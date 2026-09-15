"""Persistent native orbit worker. Numeric input is derived only from decoded seeds."""
from __future__ import annotations

import json
import math
from copy import deepcopy
from pathlib import Path
import subprocess
import tempfile
import threading

from orbit_seed import feedback_luts, _encode, digest
from orbit_dynamics import validate_model


def numeric_model(model, transport_version=3):
    """Canonical worker transport, never a dependency outside the packed model."""
    if model.get("profile") not in ("ORBIT-DYNAMICS-R1", "ORBIT-DYNAMICS-R2"):
        raise ValueError("Unknown physical model profile")
    r2 = model["profile"] == "ORBIT-DYNAMICS-R2"
    i, f, frame = model["integration"], model["force"], model["frame"]
    legacy_version = 2 if r2 else 1
    if transport_version not in (legacy_version, 3):
        raise ValueError("Transport version does not support the physical profile")
    lines = ["ORBIT-SEED-NATIVE-" + str(transport_version)]
    def add(values):
        if any(not math.isfinite(float(v)) for v in values):
            raise ValueError("Nonfinite native model parameter")
        lines.append(" ".join(str(v) if type(v) is int else format(float(v), ".17g") for v in values))
    if transport_version == 3:
        lines.append("DYNAMICS " + str(legacy_version))
        lines.append("DOMAIN " + " ".join(format(float(v), ".17g") for v in model["domain_s"]))
    add([model["epoch_gpst_s"], model["epoch_jd_tt"], i["step_s"], i["checkpoint_stride_steps"],
         i["max_checkpoints"], i["max_steps_per_query"]])
    if len(model["state_gcrs"]) != 6: raise ValueError("Six-component state required")
    add(model["state_gcrs"])
    add([f.get(k, 0.) for k in ("mu_m3_s2", "radius_m", "j2", "j3", "j4", "c22", "s22",
                       "sun_mu_m3_s2", "moon_mu_m3_s2", "au_m", "srp_m_s2_at_au")]
        + [int(f["shadow"])] + f["empirical_rtn_m_s2"])
    add([frame.get(k, 0.) for k in ("era0_rad", "era_rate_rad_s", "xp_rad", "yp_rad")])
    def series(name, segments, components):
        if not segments: raise ValueError("Empty coefficient series")
        lines.append(name + " " + str(len(segments)))
        for segment in segments:
            rows = segment["coefficients"]
            if len(rows) != components or not rows[0] or any(len(r) != len(rows[0]) for r in rows):
                raise ValueError("Malformed coefficient array")
            add([segment["t0_s"], segment["t1_s"], len(rows[0]) - 1])
            for row in rows: add(row)
    for name, segments, components in (("Q", frame["q_segments"], 9),
                                       ("SUN", model["forcing"]["sun"], 3),
                                       ("MOON", model["forcing"]["moon"], 3)):
        series(name, segments, components)
    if r2:
        degree = f["gravity_degree"]
        lines.append("GRAVITY " + str(degree))
        for n in range(degree + 1):
            for m in range(n + 1): add([f["gravity_c"][n][m], f["gravity_s"][n][m]])
        lines.append("RELATIVITY " + str(int(f["relativity"])) + " " + format(f["c_m_s"], ".17g"))
        series("EOP", frame["eop_segments"], 3)
    lines.append("END")
    return "\n".join(lines) + "\n"


class NativeOrbit:
    def __init__(self, worker_path, model, backend="cpu"):
        self.model, self.backend = deepcopy(validate_model(model)), backend
        self.model_sha256 = digest(self.model)
        self._domain = tuple(self.model["domain_s"])
        if backend not in ("cpu", "cuda"): raise ValueError("Backend must be cpu or cuda")
        self._lock = threading.RLock()
        self._feedback_key, self._feedback_values = None, None
        self._temporary = tempfile.TemporaryDirectory(prefix="atomos_orbit_")
        self._model_path = Path(self._temporary.name) / "model.txt"
        self._model_path.write_text(numeric_model(self.model), encoding="ascii")
        self._errors = (Path(self._temporary.name) / "worker.stderr").open("w+", encoding="utf-8")
        try:
            self.process = subprocess.Popen([str(Path(worker_path).resolve()), "--model", str(self._model_path),
                                             "--backend", backend], stdin=subprocess.PIPE, stdout=subprocess.PIPE,
                                            stderr=self._errors, text=True, encoding="utf-8", bufsize=1,
                                            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0))
            self.ready = self._read()
            if self.ready.get("type") != "ready" or self.ready.get("protocol") != "ORBIT-WORKER-1":
                raise RuntimeError("Native worker rejected model: " + str(self.ready))
        except Exception:
            self.close()
            raise

    def _read(self):
        line = self.process.stdout.readline()
        if not line:
            self._errors.flush()
            self._errors.seek(0)
            raise RuntimeError("Native worker closed: " + self._errors.read()[-4000:])
        result = json.loads(line)
        if result.get("type") == "error" or result.get("error") or result.get("status") in ("error", "ERROR"):
            raise RuntimeError("Native worker error: " + str(result))
        return result

    def command(self, text):
        with self._lock:
            self.process.stdin.write(text + "\n")
            self.process.stdin.flush()
            return self._read()

    def _time(self, time_s):
        time_s = float(time_s)
        if not math.isfinite(time_s) or not self._domain[0] <= time_s <= self._domain[1]:
            raise ValueError("Timestamp outside the packed model domain")
        return time_s

    def query(self, time_s):
        result = self.command("QUERY " + format(self._time(time_s), ".17g"))
        if "queries" in result:
            if len(result["queries"]) != 1: raise RuntimeError("Native query cardinality mismatch")
            return {**{k: v for k, v in result.items() if k != "queries"}, **result["queries"][0]}
        return result

    def batch(self, times):
        times = [self._time(t) for t in times]
        result = []
        for start in range(0, len(times), 4096):
            part = times[start:start + 4096]
            reply = self.command("BATCH " + str(len(part)) + " " + " ".join(format(t, ".17g") for t in part))
            rows = reply.get("queries", reply.get("results"))
            if not isinstance(rows, list) or len(rows) != len(part):
                raise RuntimeError("Native batch response cardinality mismatch")
            result.extend(rows)
        return result

    def transition(self, feedback, q, drive):
        with self._lock:
            # Typed canonical bytes distinguish lists/tuples, bools/ints and signed zero.
            # The whole editable object is keyed so invalid edits cannot bypass validation.
            key = _encode(feedback)
            if key != self._feedback_key:
                luts = feedback_luts(feedback)
                fixed = [feedback["present"]]
                for masks in feedback["sets"]:
                    fixed.extend(masks[k] for k in ("asa_mask", "na_mask", "boundary_mask"))
                fixed.extend(luts[k] for k in ("x_lut", "j_lut", "k_lut"))
                self._feedback_key, self._feedback_values = key, tuple(fixed)
            values = [q, drive, *self._feedback_values]
            return self.command("TRANSITION " + " ".join(str(v) for v in values))

    def stats(self): return self.command("STATS")
    def reset(self): return self.command("RESET")

    def close(self):
        process = getattr(self, "process", None)
        if process is not None and process.poll() is None:
            try:
                process.stdin.write("QUIT\n")
                process.stdin.flush()
                process.wait(timeout=3)
            except (OSError, subprocess.TimeoutExpired):
                process.kill()
                process.wait(timeout=3)
        if process is not None:
            if process.stdin: process.stdin.close()
            if process.stdout: process.stdout.close()
        errors = getattr(self, "_errors", None)
        if errors is not None: errors.close()
        temporary = getattr(self, "_temporary", None)
        if temporary is not None: temporary.cleanup()

    def __enter__(self): return self
    def __exit__(self, *_): self.close()
