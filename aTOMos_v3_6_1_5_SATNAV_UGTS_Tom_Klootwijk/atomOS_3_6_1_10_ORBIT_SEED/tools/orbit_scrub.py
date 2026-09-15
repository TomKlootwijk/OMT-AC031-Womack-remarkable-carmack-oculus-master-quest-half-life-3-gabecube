#!/usr/bin/env python3
"""Local timestamp scrubber. Every query reconstructs from a verified compact seed."""
from __future__ import annotations
import argparse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
import json
from pathlib import Path
import sys
import threading
from urllib.parse import parse_qs, urlparse

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "python"))
from orbit_native import NativeOrbit
from orbit_query import OrbitSession, predicate_word, station_events
from orbit_seed import digest, inspect_bytes, load


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument("--seeds", type=Path, default=ROOT / "examples/orbit/seeds")
    p.add_argument("--worker", type=Path, default=ROOT / "bin/cpu/orbit_worker.exe")
    p.add_argument("--backend", choices=("cpu", "cuda"), default="cpu")
    p.add_argument("--accuracy", type=Path, default=ROOT / "results/orbit_accuracy_r2_cpu_verified/accuracy_summary.json")
    p.add_argument("--port", type=int, default=3619)
    args = p.parse_args()
    paths = sorted(args.seeds.glob("*.orbseed"))
    if not paths: p.error("No .orbseed files found")
    seeds, workers, locks = {}, {}, {}
    for path in paths:
        seed = load(path); name = seed["object"]["id"]
        if name in seeds: raise ValueError("Duplicate object ID")
        seeds[name] = {"seed": seed, "info": inspect_bytes(path.read_bytes())}
        workers[name] = NativeOrbit(args.worker, seed["model"], args.backend)
        locks[name] = threading.Lock()
    page_path = ROOT / "web/orbit_scrubber.html"
    accuracy_path = args.accuracy

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_): pass
        def send(self, code, value, content_type="application/json; charset=utf-8"):
            data = value if isinstance(value, bytes) else json.dumps(value, allow_nan=False, separators=(",", ":")).encode()
            self.send_response(code)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(data)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            try: self.wfile.write(data)
            except (BrokenPipeError, ConnectionResetError): pass
        def do_GET(self):
            parsed = urlparse(self.path)
            if parsed.path == "/": return self.send(200, page_path.read_bytes(), "text/html; charset=utf-8")
            if parsed.path == "/api/info":
                return self.send(200, {"version": "3.6.1.10", "backend": args.backend,
                    "objects": [{**v["info"], "model_epoch_gpst_s": v["seed"]["model"]["epoch_gpst_s"],
                                 "domain_s": v["seed"]["model"]["domain_s"], "stations": v["seed"]["stations"],
                                 "feedback": v["seed"]["feedback"]} for v in seeds.values()]})
            if parsed.path == "/api/accuracy":
                if accuracy_path.exists():
                    params = parse_qs(parsed.query)
                    name = params.get("object", [None])[0]
                    if name not in seeds: return self.send(400, {"error": "A loaded object ID is required"})
                    report = json.loads(accuracy_path.read_text())
                    row = next((r for r in report["objects"] if r["object_id"] == name), None)
                    actual_hash = digest(seeds[name]["seed"]["model"])
                    if row is None or row.get("physical_model_sha256") != actual_hash:
                        return self.send(200, {"status": "unvalidated_model", "physical_model_sha256": actual_hash,
                            "message": "The loaded physical seed differs from the model in the archived accuracy report"})
                    return self.send(200, {"status": "matched_physical_model", "qualification": report["qualification"],
                                          "physical_model_sha256": actual_hash, "validation": row})
                return self.send(200, {"status": "Validation report not loaded; model-domain membership is not an accuracy claim"})
            if parsed.path not in ("/api/query", "/api/events", "/api/schedule"):
                return self.send(404, {"error": "Unknown endpoint"})
            try:
                q = parse_qs(parsed.query, strict_parsing=True)
                name = q["object"][0]
                if name not in seeds: raise ValueError("Unknown object")
                seed = seeds[name]["seed"]
                station = q.get("station", [seed["stations"][0]["id"]])[0]
                with locks[name]:
                    worker = workers[name]
                    session = OrbitSession(seed, worker, station)
                    t = float(q.get("time_s", [0.])[0])
                    if parsed.path == "/api/query":
                        result = session.query(t)
                        feedback = seed["feedback"]
                        drive = predicate_word(feedback, result, t, session.station)
                        result["feedback_snapshot"] = worker.transition(feedback, feedback["q0"], drive)
                        result["feedback_scope"] = "One transition from packed q0 at this timestamp; ordered playback uses /api/schedule"
                        result["cache"] = worker.stats()
                    else:
                        end = min(seed["model"]["domain_s"][1], t + float(q.get("duration_s", [86400.])[0]))
                        if parsed.path == "/api/events": result = station_events(session, t, end)
                        else:
                            rows = list(session.schedule(t, end))
                            result = {"queries": len(rows), "start_s": t, "end_s": end,
                                      "states": [{"time_s": r["time_s"], "q": r["feedback"]["after"],
                                                  "next_dt_s": r["chosen_next_dt_s"]} for r in rows],
                                      "final_record_sha256": rows[-1]["record_sha256"], "cache": worker.stats()}
                self.send(200, result)
            except (KeyError, ValueError, RuntimeError) as exc:
                self.send(400, {"error": str(exc)})

    server = ThreadingHTTPServer(("127.0.0.1", args.port), Handler)
    print(f"ORBIT-SEED-R1 scrubber: http://127.0.0.1:{args.port}", flush=True)
    try: server.serve_forever()
    except KeyboardInterrupt: pass
    finally:
        server.server_close()
        for worker in workers.values(): worker.close()


if __name__ == "__main__": main()
