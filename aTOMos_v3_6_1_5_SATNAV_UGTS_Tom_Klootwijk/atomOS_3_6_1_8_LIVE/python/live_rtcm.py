"""Incremental RTCM3 GPS code receiver and bounded TCP/NTRIP input.

This is an independently written parser; RTKLIB and pyrtcm were consulted for
field definitions. It estimates no positions and never substitutes absent ranges.
The caller supplies a GPST reference when decoding an archived capture.
"""
from __future__ import annotations

import base64
from collections import Counter
import hashlib
import json
import math
from pathlib import Path
import socket
import ssl
import time
from typing import Callable
from urllib.parse import unquote, urlsplit

C = 299792458.0
RANGE_MS = C * .001
WEEK = 604800.0
GPS_UNIX_EPOCH = 315964800.0
GPS_SIGNALS = {
    2: "C1C", 3: "C1P", 4: "C1W", 5: "C1Y", 6: "C1M",
    8: "C2C", 9: "C2P", 10: "C2W", 11: "C2Y", 12: "C2M",
    15: "C2S", 16: "C2L", 17: "C2X", 22: "C5I", 23: "C5Q",
    24: "C5X", 30: "C1S", 31: "C1L", 32: "C1X",
}
URA = (2.4, 3.4, 4.85, 6.85, 9.65, 13.65, 24., 48., 96., 192.,
       384., 768., 1536., 3072., 6144., None)


class RTCMError(ValueError):
    pass


class CallbackFailure(RuntimeError):
    """Application callback failed; reconnecting cannot repair application errors."""


class Bits:
    def __init__(self, data: bytes):
        self.data, self.pos = data, 0

    def u(self, count: int) -> int:
        if count < 0 or self.pos + count > 8 * len(self.data):
            raise RTCMError(f"truncated field at bit {self.pos}, requires {count}")
        result = 0
        for index in range(self.pos, self.pos + count):
            result = (result << 1) | ((self.data[index // 8] >> (7 - index % 8)) & 1)
        self.pos += count
        return result

    def s(self, count: int) -> int:
        value = self.u(count)
        return value - (1 << count) if value & (1 << (count - 1)) else value

    def end(self):
        remaining = 8 * len(self.data) - self.pos
        if remaining > 7 or (remaining and self.u(remaining)):
            raise RTCMError("unexpected payload length or nonzero padding")


def crc24q(data: bytes) -> int:
    crc = 0
    for octet in data:
        crc ^= octet << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return crc & 0xffffff


def frame(payload: bytes) -> bytes:
    """Frame an existing payload, primarily for deterministic parser tests."""
    if not 2 <= len(payload) <= 1023:
        raise ValueError("RTCM payload length must be 2..1023 bytes")
    body = bytes((0xD3, len(payload) >> 8, len(payload) & 255)) + payload
    return body + crc24q(body).to_bytes(3, "big")


def unix_to_gpst(unix_s: float, gps_utc_offset_s: int = 18) -> float:
    """Offset is explicit input, not an automatically updated leap-second table."""
    return unix_s - GPS_UNIX_EPOCH + gps_utc_offset_s


def nearest_tow(tow: float, reference_gpst_s: float) -> float:
    if not math.isfinite(tow) or not 0 <= tow < WEEK:
        raise RTCMError("GPS time of week outside [0,604800)")
    return tow + math.floor((reference_gpst_s - tow) / WEEK + .5) * WEEK


def _msm_header(b: Bits, message_type: int, reference: float, leap: int) -> dict:
    station = b.u(12)
    raw_time = b.u(30)
    constellation = {107: "GPS", 108: "GLONASS", 109: "Galileo", 110: "SBAS",
                     111: "QZSS", 112: "BeiDou"}[message_type // 10]
    if constellation == "GLONASS":
        dow, tod = raw_time >> 27, (raw_time & ((1 << 27) - 1)) * .001
        if dow > 6 or tod >= 86400:
            raise RTCMError("invalid GLONASS MSM day/time")
        tow = (dow * 86400 + tod - 10800 + leap) % WEEK
    else:
        tow = raw_time * .001
        if tow >= WEEK:
            raise RTCMError("invalid MSM time of week")
        if constellation == "BeiDou":
            tow = (tow + 14) % WEEK
    result = dict(type="observation_fragment", message_type=message_type,
                  station_id=station, time_gpst_s=nearest_tow(tow, reference),
                  raw_epoch=raw_time, constellation=constellation,
                  multiple_message=bool(b.u(1)), issue_of_data_station=b.u(3),
                  reserved_session=b.u(7), clock_steering=b.u(2), external_clock=b.u(2),
                  smoothing=bool(b.u(1)), smoothing_interval=b.u(3))
    sats = [i for i in range(1, 65) if b.u(1)]
    signals = [i for i in range(1, 33) if b.u(1)]
    cells = [(i, sig) for i in range(len(sats)) for sig in signals if b.u(1)]
    if len(cells) > 64:
        raise RTCMError("MSM has more than 64 active signal cells")
    result.update(satellites=sats, signal_ids=signals, cells=cells)
    return result


def _decode_msm(b: Bits, message_type: int, reference: float, leap: int) -> dict:
    out = _msm_header(b, message_type, reference, leap)
    if out["constellation"] != "GPS" or message_type % 10 not in (4, 5, 6, 7):
        satbits, cellbits = {1: (10, 15), 2: (10, 27), 3: (10, 42),
            4: (18, 48), 5: (36, 63), 6: (18, 65), 7: (36, 80)}[message_type % 10]
        b.u(len(out["satellites"]) * satbits + len(out["cells"]) * cellbits)
        b.end()
        out.update(observations=[], unsupported_observations=True)
        return out  # Common header still closes a mixed-constellation sequence.
    high = message_type % 10 in (6, 7)
    rates = message_type % 10 in (5, 7)
    sats, cells = out["satellites"], out["cells"]
    rough = [b.u(8) for _ in sats]
    extended = [b.u(4) for _ in sats] if rates else [None for _ in sats]
    modulo = [b.u(10) for _ in sats]
    rough_rate = [b.s(14) for _ in sats] if rates else [None for _ in sats]
    fine = [b.s(20 if high else 15) for _ in cells]
    phase = [b.s(24 if high else 22) for _ in cells]
    lock = [b.u(10 if high else 4) for _ in cells]
    half = [bool(b.u(1)) for _ in cells]
    cnr = [b.u(10 if high else 6) * (.0625 if high else 1) for _ in cells]
    fine_rate = [b.s(15) for _ in cells] if rates else [None for _ in cells]
    b.end()
    observations = []
    for j, (satindex, signal) in enumerate(cells):
        prn = sats[satindex]
        status = "valid"
        if rough[satindex] == 255:
            status = "missing_rough_range"
        elif fine[j] == -(1 << (19 if high else 14)):
            status = "missing_fine_pseudorange"
        elif prn > 32:
            status = "unsupported_gps_prn"
        elif signal not in GPS_SIGNALS:
            status = "unsupported_signal"
        base = (rough[satindex] + modulo[satindex] * 2**-10) * RANGE_MS
        value = base + fine[j] * 2**(-29 if high else -24) * RANGE_MS
        if status == "valid" and value <= 0:
            status = "nonpositive_pseudorange"
        observations.append(dict(prn=prn, signal_id=signal,
            code=GPS_SIGNALS.get(signal), pseudorange_m=value if status == "valid" else None,
            pseudorange_resolution_m=RANGE_MS * 2**(-29 if high else -24),
            cn0_dbhz=cnr[j] if cnr[j] else None, status=status,
            rough_range_ms=rough[satindex], rough_modulo=modulo[satindex],
            fine_pseudorange=fine[j], fine_phase_range=phase[j],
            lock_indicator=lock[j], half_cycle_ambiguity=half[j],
            extended_satellite_information=extended[satindex],
            rough_phase_range_rate=rough_rate[satindex], fine_phase_range_rate=fine_rate[j]))
    out.update(observations=observations, unsupported_observations=False)
    return out


def _decode_legacy(b: Bits, reference: float) -> dict:
    out = dict(type="observation_fragment", message_type=1004, station_id=b.u(12))
    tow = b.u(30) * .001
    out.update(time_gpst_s=nearest_tow(tow, reference), constellation="GPS",
               multiple_message=bool(b.u(1)))
    nsat = b.u(5)
    out.update(smoothing=bool(b.u(1)), smoothing_interval=b.u(3))
    observations = []
    for _ in range(nsat):
        prn, l1code, raw_pr, phase1, lock1 = b.u(6), b.u(1), b.u(24), b.s(20), b.u(7)
        ambiguity, cnr1 = b.u(8), b.u(8) * .25
        l2code, delta, phase2, lock2, cnr2 = b.u(2), b.s(14), b.s(20), b.u(7), b.u(8) * .25
        pr = raw_pr * .02 + ambiguity * RANGE_MS
        for code, value, cnr, phase, lock, missing in [
            ("C1P" if l1code else "C1C", pr, cnr1, phase1, lock1, False),
            (("C2X", "C2P", "C2D", "C2W")[l2code], pr + delta * .02,
             cnr2, phase2, lock2, delta == -8192),
        ]:
            status = "unsupported_gps_prn" if not 1 <= prn <= 32 else (
                "missing_pseudorange_difference" if missing else "valid")
            if status == "valid" and value <= 0:
                status = "nonpositive_pseudorange"
            observations.append(dict(prn=prn, code=code, signal_id=None,
                pseudorange_m=value if status == "valid" else None,
                pseudorange_resolution_m=.02,
                cn0_dbhz=cnr if cnr else None, status=status,
                phase_difference_raw=phase, lock_indicator=lock))
    b.end()
    out.update(observations=observations, unsupported_observations=False)
    return out


def _decode_station(b: Bits, message_type: int) -> dict:
    station, itrf = b.u(12), b.u(6)
    gps, glo, gal, reference = b.u(1), b.u(1), b.u(1), b.u(1)
    x, oscillator, reserved = b.s(38) * .0001, b.u(1), b.u(1)
    y, quarter = b.s(38) * .0001, b.u(2)
    z = b.s(38) * .0001
    height = b.u(16) * .0001 if message_type == 1006 else None
    b.end()
    return dict(type="station", station_id=station, message_type=message_type,
                ecef_arp_m=[x, y, z], antenna_height_m=height, itrf_realization=itrf,
                gps_indicator=gps, glonass_indicator=glo, galileo_indicator=gal,
                reference_station_indicator=reference, single_receiver_oscillator=oscillator,
                quarter_cycle_indicator=quarter, reserved_bit=reserved)


def _decode_ephemeris(b: Bits, reference: float) -> dict:
    prn, week_mod, ura_index, l2code = b.u(6), b.u(10), b.u(4), b.u(2)
    week = week_mod + 1024 * math.floor((reference / WEEK - week_mod) / 1024 + .5)
    e = dict(prn=prn, week=week, idot=b.s(14) * 2**-43 * math.pi, iode=b.u(8))
    toc = b.u(16) * 16.
    e.update(af2=b.s(8) * 2**-55, af1=b.s(16) * 2**-43, af0=b.s(22) * 2**-31,
             iodc=b.u(10), crs=b.s(16) * 2**-5, delta_n=b.s(16) * 2**-43 * math.pi,
             m0=b.s(32) * 2**-31 * math.pi, cuc=b.s(16) * 2**-29,
             ecc=b.u(32) * 2**-33, cus=b.s(16) * 2**-29, sqrt_a=b.u(32) * 2**-19)
    toe = b.u(16) * 16.
    e.update(cic=b.s(16) * 2**-29, omega0=b.s(32) * 2**-31 * math.pi,
             cis=b.s(16) * 2**-29, i0=b.s(32) * 2**-31 * math.pi,
             crc=b.s(16) * 2**-5, w=b.s(32) * 2**-31 * math.pi,
             omega_dot=b.s(24) * 2**-43 * math.pi, tgd=b.s(8) * 2**-31,
             health=b.u(6))
    l2flag, fit_flag = b.u(1), b.u(1)
    b.end()
    if not 1 <= prn <= 32 or toe >= WEEK or toc >= WEEK or not 0 < e["sqrt_a"]:
        raise RTCMError("GPS ephemeris domain invalid")
    # RTCM carries a truncated week. Choose its nearest 1024-week realization;
    # toc may lie across a weekly boundary relative to toe.
    e.update(toe=week * WEEK + toe, toc=nearest_tow(toc, week * WEEK + toe),
             ura_m=URA[ura_index], fit_interval_hours=4. if fit_flag == 0 else 0.,
             source="RTCM1019")
    return dict(type="ephemeris", message_type=1019, ephemeris=e,
                week_mod1024=week_mod, ura_index=ura_index, l2_code=l2code,
                l2_p_data_flag=l2flag, fit_flag=fit_flag,
                fit_interval_status="four_hours" if fit_flag == 0 else "greater_than_four_unspecified")


class RTCMDecoder:
    """CRC framing plus conservative station/epoch fragment assembly.

    feed returns message and status events. Epoch events contain all decoded GPS
    signals; epoch_from_event makes explicit code selection for the position model.
    A new timestamp, gap, reconnect or EOF discards an unterminated assembly.
    """
    def __init__(self, reference_gpst_s: float, gps_utc_offset_s: int = 18):
        if not math.isfinite(reference_gpst_s) or reference_gpst_s < 0:
            raise ValueError("a finite nonnegative GPST reference is required")
        self.reference = float(reference_gpst_s)
        self.leap = gps_utc_offset_s
        self.buffer = bytearray()
        self.offset = 0
        self.pending = None
        self.counts = Counter()
        self.last_epochs = {}

    def _abandon(self, reason: str) -> list[dict]:
        if self.pending is None:
            return []
        result = dict(type="incomplete_epoch", reason=reason, **self.pending)
        self.pending = None
        return [result]

    def reset(self, reason: str = "reconnect") -> list[dict]:
        result = self.finish(reason)
        self.last_epochs.clear()
        return result

    def finish(self, reason: str = "end_of_input") -> list[dict]:
        result = self._abandon(reason)
        if self.buffer:
            result.append(dict(type="truncated", reason=reason, offset=self.offset,
                               bytes=len(self.buffer), raw_hex=self.buffer.hex()))
            self.offset += len(self.buffer)
            self.buffer.clear()
        return result

    def _assemble(self, event: dict) -> list[dict]:
        result = []
        key = (event["station_id"], event["time_gpst_s"])
        if self.pending and key != (self.pending["station_id"], self.pending["time_gpst_s"]):
            result += self._abandon("station_or_epoch_changed_before_terminal")
        if self.pending is None:
            self.pending = dict(station_id=key[0], time_gpst_s=key[1], observations=[],
                fragment_message_types=[], fragment_sha256=[],
                reception_gpst_s=event["reception_gpst_s"],
                first_fragment_reception_gpst_s=event["reception_gpst_s"],
                sequence_start="not_identifiable_from_rtcm_mmi")
        self.pending["fragment_message_types"].append(event["message_type"])
        self.pending["fragment_sha256"].append(event["raw_sha256"])
        self.pending["observations"].extend(event["observations"])
        if not event["multiple_message"]:
            complete = self.pending
            self.pending = None
            complete["terminal_reception_gpst_s"] = event["reception_gpst_s"]
            complete["reception_gpst_s"] = event["reception_gpst_s"]
            # Cross-message duplication of a satellite/signal must not become
            # duplicate geometry rows or silently override different observations.
            seen = {}
            for ob in complete["observations"]:
                signal_key = (ob["prn"], ob["code"], ob["signal_id"])
                if signal_key in seen and seen[signal_key] != ob:
                    return result + [dict(type="incomplete_epoch", reason="conflicting_signal_fragments", **complete)]
                seen[signal_key] = ob
            complete["observations"] = list(seen.values())
            last = self.last_epochs.get(key[0])
            if last is not None and key[1] <= last:
                result.append(dict(type="stale_epoch", reason="nonincreasing_station_epoch", **complete))
            elif complete["observations"]:
                self.last_epochs[key[0]] = key[1]
                result.append(dict(type="epoch", status="terminal_received", **complete))
            else:
                result.append(dict(type="unsupported_epoch", **complete))
        return result

    def feed(self, data: bytes, reception_gpst_s: float | None = None) -> list[dict]:
        reference = self.reference if reception_gpst_s is None else float(reception_gpst_s)
        if not math.isfinite(reference) or reference < 0:
            raise ValueError("reception GPST must be finite and nonnegative")
        self.buffer.extend(data)
        result = []
        while self.buffer:
            if self.buffer[0] != 0xD3:
                n = self.buffer.find(0xD3)
                n = len(self.buffer) if n < 0 else n
                result.append(dict(type="noise", offset=self.offset, bytes=n))
                del self.buffer[:n]
                self.offset += n
                continue
            if len(self.buffer) < 3:
                break
            length = ((self.buffer[1] & 3) << 8) | self.buffer[2]
            if self.buffer[1] & 0xFC or length < 2:
                result += self._abandon("invalid_frame_header")
                result.append(dict(type="malformed_header", offset=self.offset))
                del self.buffer[0]
                self.offset += 1
                continue
            size = length + 6
            if len(self.buffer) < size:
                break
            raw = bytes(self.buffer[:size])
            if crc24q(raw[:-3]) != int.from_bytes(raw[-3:], "big"):
                result += self._abandon("crc_error")
                result.append(dict(type="crc_error", offset=self.offset, raw_hex=raw.hex()))
                del self.buffer[0]
                self.offset += 1
                continue
            offset = self.offset
            del self.buffer[:size]
            self.offset += size
            b = Bits(raw[3:-3])
            message_type = b.u(12)
            common = dict(message_type=message_type, offset=offset,
                          raw_hex=raw.hex(), raw_sha256=hashlib.sha256(raw).hexdigest(),
                          reception_gpst_s=reference, reference_gpst_s=reference)
            try:
                if message_type == 1019:
                    decoded = _decode_ephemeris(b, reference)
                elif message_type in (1005, 1006):
                    decoded = _decode_station(b, message_type)
                elif message_type == 1004:
                    decoded = _decode_legacy(b, reference)
                elif 107 <= message_type // 10 <= 112 and 1 <= message_type % 10 <= 7:
                    decoded = _decode_msm(b, message_type, reference, self.leap)
                else:
                    decoded = dict(type="unsupported")
                event = {**common, **decoded}
                self.counts[str(message_type)] += 1
                result.append(event)
                if event["type"] == "observation_fragment":
                    result.extend(self._assemble(event))
            except RTCMError as exc:
                result += self._abandon("malformed_message")
                result.append(dict(type="malformed", reason=str(exc), **common))
        return result


def ephemeris_from_event(event: dict):
    from live_gnss import GPSEphemeris
    if event["type"] != "ephemeris":
        raise ValueError("expected ephemeris event")
    data = dict(event["ephemeris"])
    if data["ura_m"] is None:
        raise RTCMError("URA index15 supplies no accuracy prediction")
    return GPSEphemeris(**data)


def epoch_from_event(event: dict, code_priority: tuple[str, ...] = ("C1C",), sigma_m: float = 3.):
    """Choose one explicitly supported code per GPS satellite, retaining omissions."""
    from live_gnss import GPSEpoch, GPSObservation
    if event["type"] != "epoch":
        raise ValueError("expected completed epoch event")
    selected, omitted = {}, []
    for ob in event["observations"]:
        if ob["status"] != "valid" or ob["code"] not in code_priority:
            omitted.append(ob)
            continue
        prior = selected.get(ob["prn"])
        rank = (code_priority.index(ob["code"]), ob["pseudorange_resolution_m"])
        if prior is None or rank < (code_priority.index(prior["code"]), prior["pseudorange_resolution_m"]):
            selected[ob["prn"]] = ob
    observations = tuple(GPSObservation(prn=prn, pseudorange_m=ob["pseudorange_m"],
        code=ob["code"], sigma_m=sigma_m, cn0_dbhz=ob["cn0_dbhz"])
        for prn, ob in sorted(selected.items()))
    metadata = {k: v for k, v in event.items() if k != "observations"}
    metadata.update(code_priority=list(code_priority), omitted_signals=omitted,
                    selected_signals=[dict(prn=prn, code=ob["code"], signal_id=ob["signal_id"],
                        pseudorange_resolution_m=ob["pseudorange_resolution_m"])
                        for prn, ob in sorted(selected.items())],
                    receiver_clock_convention="RTCM epoch and pseudorange are receiver clock tagged; clock solved downstream")
    return GPSEpoch(time_gpst_s=event["time_gpst_s"], observations=observations, source_metadata=metadata)


class ChunkedBody:
    """Incremental HTTP chunked-transfer decoder with explicit terminal/truncation."""
    def __init__(self):
        self.buffer = bytearray()
        self.remaining = None
        self.need_crlf = False
        self.trailers = False
        self.done = False

    def feed(self, data: bytes) -> list[bytes]:
        if self.done and data:
            raise RTCMError("bytes after HTTP chunked terminal")
        self.buffer.extend(data)
        output = []
        while self.buffer and not self.done:
            if self.need_crlf:
                if len(self.buffer) < 2:
                    break
                if self.buffer[:2] != b"\r\n":
                    raise RTCMError("invalid chunk terminator")
                del self.buffer[:2]
                self.need_crlf = False
            elif self.remaining is not None:
                count = min(self.remaining, len(self.buffer))
                output.append(bytes(self.buffer[:count]))
                del self.buffer[:count]
                self.remaining -= count
                if self.remaining == 0:
                    self.remaining, self.need_crlf = None, True
            else:
                line_end = self.buffer.find(b"\r\n")
                if line_end < 0:
                    if len(self.buffer) > 8192:
                        raise RTCMError("HTTP chunk line exceeds 8192 bytes")
                    break
                line = bytes(self.buffer[:line_end])
                del self.buffer[:line_end + 2]
                if self.trailers:
                    if not line:
                        self.done = True
                        if self.buffer:
                            raise RTCMError("bytes after HTTP trailers")
                    continue
                size_text = line.split(b";", 1)[0]
                if not size_text or any(c not in b"0123456789abcdefABCDEF" for c in size_text):
                    raise RTCMError("invalid HTTP chunk size")
                size = int(size_text, 16)
                if size > 64 * 1024 * 1024:
                    raise RTCMError("HTTP individual chunk exceeds 64MiB")
                if size == 0:
                    self.trailers = True
                else:
                    self.remaining = size
        return output

    def finish(self):
        if not self.done:
            raise RTCMError("truncated HTTP chunked body")


def redact_url(url: str) -> str:
    u = urlsplit(url)
    return f"{u.scheme}://{u.hostname}" + (f":{u.port}" if u.port else "") + (u.path or "/")


def capture(url: str, raw_path: str | Path, seconds: float = 30., max_bytes: int = 8 * 1024 * 1024,
            timeout: float = 5., reconnects: int = 2, gps_utc_offset_s: int = 18,
            on_chunk: Callable[[bytes, float], None] | None = None,
            on_event: Callable[[dict], None] | None = None,
            username: str | None = None, password: str | None = None) -> dict:
    """Read a bounded stream, keeping raw transport body and timing/boundary records.

    Supported schemes: tcp, ntrip, ntrips, http, https. No GGA or receiver commands
    are sent. HTTP/NTRIP uses only GET. Credentials are absent from stored metadata.
    The raw output path and its .timing.jsonl/.json siblings must not already exist.
    """
    if seconds <= 0 or max_bytes <= 0 or timeout <= 0 or reconnects < 0:
        raise ValueError("capture duration, byte bound and timeout must be positive")
    u = urlsplit(url)
    if u.scheme not in ("tcp", "ntrip", "ntrips", "http", "https") or not u.hostname:
        raise ValueError("use tcp/ntrip/ntrips/http/https URL with a host")
    secure = u.scheme in ("https", "ntrips")
    port = u.port or (443 if secure else 2101 if u.scheme == "ntrip" else 80)
    if u.scheme == "tcp" and u.port is None:
        raise ValueError("TCP URL requires a port")
    raw_path = Path(raw_path)
    sidecar, report_path = Path(str(raw_path) + ".timing.jsonl"), Path(str(raw_path) + ".json")
    if any(p.exists() for p in (raw_path, sidecar, report_path)):
        raise FileExistsError("capture output or sidecars already exist")
    raw_path.parent.mkdir(parents=True, exist_ok=True)
    started_unix, started = time.time(), time.monotonic()
    deadline = started + seconds
    total, connections = 0, 0
    transport_events = []
    digest = hashlib.sha256()
    stop_reason = "duration_limit"
    login = username if username is not None else unquote(u.username or "")
    secret = password if password is not None else unquote(u.password or "")

    with raw_path.open("xb") as raw_file, sidecar.open("x", encoding="utf-8") as timing:
        def emit(kind, **fields):
            event = dict(type=kind, connection=connections, offset=total,
                         utc_unix_s=time.time(), **fields)
            transport_events.append(event)
            timing.write(json.dumps(event, allow_nan=False) + "\n")
            timing.flush()
            if on_event:
                try:
                    on_event(event)
                except Exception as exc:
                    raise CallbackFailure("capture event callback failed") from exc

        def save(data):
            nonlocal total
            data = data[:max_bytes - total]
            if not data:
                return
            received = time.time()
            gpst = unix_to_gpst(received, gps_utc_offset_s)
            raw_file.write(data)
            raw_file.flush()
            digest.update(data)
            timing.write(json.dumps(dict(type="chunk", connection=connections, offset=total,
                bytes=len(data), utc_unix_s=received, reception_gpst_s=gpst)) + "\n")
            timing.flush()
            total += len(data)
            if on_chunk:
                try:
                    on_chunk(data, gpst)
                except Exception as exc:
                    raise CallbackFailure("capture chunk callback failed") from exc

        for attempt in range(reconnects + 1):
            if time.monotonic() >= deadline or total >= max_bytes:
                break
            connections += 1
            sock = None
            emit("connecting")
            try:
                sock = socket.create_connection((u.hostname, port), min(timeout, deadline - time.monotonic()))
                if secure:
                    sock = ssl.create_default_context().wrap_socket(sock, server_hostname=u.hostname)
                sock.settimeout(min(timeout, max(.001, deadline - time.monotonic())))
                chunked = None
                body_remaining = None
                prefetched = b""
                if u.scheme != "tcp":
                    path = (u.path or "/") + ("?" + u.query if u.query else "")
                    headers = [f"GET {path} HTTP/1.1", f"Host: {u.hostname}:{port}",
                        "Ntrip-Version: Ntrip/2.0", "User-Agent: NTRIP aTOMos/3.6.1.8",
                        "Accept: */*", "Connection: close"]
                    if login or secret:
                        token = base64.b64encode((login + ":" + secret).encode()).decode()
                        headers.append("Authorization: Basic " + token)
                    sock.sendall(("\r\n".join(headers) + "\r\n\r\n").encode("ascii"))
                    header_bytes = bytearray()

                    def line(initial=b""):
                        data = bytearray(initial)
                        while not data.endswith(b"\r\n"):
                            sock.settimeout(min(timeout, max(.001, deadline - time.monotonic())))
                            if time.monotonic() >= deadline:
                                raise TimeoutError("capture deadline during HTTP header")
                            bit = sock.recv(1)
                            if not bit:
                                raise RTCMError("truncated HTTP response header")
                            data.extend(bit)
                            header_bytes.extend(bit)
                            if len(header_bytes) > 32768:
                                raise RTCMError("HTTP headers exceed 32768 bytes")
                        return bytes(data[:-2])

                    status = line()
                    words = status.split()
                    if len(words) < 2 or words[1] != b"200" or not (
                        words[0].startswith(b"HTTP/") or words[0] == b"ICY"):
                        raise RTCMError("server did not return HTTP/ICY200")
                    response_headers = {}
                    if words[0] == b"ICY":
                        # NTRIP v1 can start the RTCM bytes immediately after its
                        # single status line, or append HTTP-style header lines.
                        # Inspect one byte; never wait for CRLF inside a frame.
                        first = sock.recv(1)
                        if first == b"\xd3":
                            prefetched = first
                        elif first:
                            item = line(first)
                            while item:
                                name, sep, value = item.partition(b":")
                                if not sep:
                                    raise RTCMError("malformed optional ICY response header")
                                response_headers[name.lower()] = value.strip().lower()
                                item = line()
                        else:
                            raise RTCMError("empty ICY stream")
                        # Some public v1 casters send Content-Length:0 and then
                        # an endless RTCM stream. V1 framing is socket-until-EOF.
                    else:
                        while True:
                            item = line()
                            if not item:
                                break
                            name, sep, value = item.partition(b":")
                            if not sep:
                                raise RTCMError("malformed HTTP response header")
                            response_headers[name.lower()] = value.strip().lower()
                        encoding = response_headers.get(b"transfer-encoding", b"")
                        if encoding == b"chunked":
                            chunked = ChunkedBody()
                        elif encoding and encoding != b"identity":
                            raise RTCMError("unsupported HTTP transfer encoding")
                        if response_headers.get(b"content-encoding", b"identity") != b"identity":
                            raise RTCMError("compressed HTTP body not supported")
                        if b"content-length" in response_headers and chunked is None:
                            length_text = response_headers[b"content-length"]
                            if not length_text.isdigit():
                                raise RTCMError("invalid HTTP content length")
                            body_remaining = int(length_text)
                    emit("connected", protocol=words[0].decode("ascii"), chunked=chunked is not None)
                else:
                    emit("connected", protocol="TCP", chunked=False)
                if prefetched:
                    save(prefetched)
                while total < max_bytes and time.monotonic() < deadline and body_remaining != 0:
                    sock.settimeout(min(timeout, max(.001, deadline - time.monotonic())))
                    data = sock.recv(min(8192, max_bytes - total))
                    if not data:
                        if chunked:
                            chunked.finish()
                        if body_remaining not in (None, 0):
                            raise RTCMError("truncated HTTP content-length body")
                        emit("disconnected", reason="eof")
                        break
                    if body_remaining is not None:
                        data = data[:body_remaining]
                        body_remaining -= len(data)
                    for part in chunked.feed(data) if chunked else [data]:
                        save(part)
                    if (chunked and chunked.done) or body_remaining == 0:
                        emit("disconnected", reason="body_complete")
                        break
                if total >= max_bytes:
                    stop_reason = "byte_limit"
                    break
                if time.monotonic() >= deadline:
                    stop_reason = "duration_limit"
                    break
            except (OSError, RTCMError) as exc:
                if isinstance(exc, TimeoutError) and time.monotonic() >= deadline:
                    stop_reason = "duration_limit"
                    emit("disconnected", reason="duration_limit")
                    break
                # Error class and controlled parser text avoid credential leakage.
                reason = str(exc) if isinstance(exc, RTCMError) else type(exc).__name__
                emit("transport_error", reason=reason)
            finally:
                if sock is not None:
                    sock.close()
            if attempt == reconnects:
                stop_reason = "reconnect_limit"
            elif time.monotonic() < deadline:
                emit("reconnecting")
        emit("capture_end", reason=stop_reason)
    report = dict(source=redact_url(url), raw_path=str(raw_path), bytes=total,
        sha256=digest.hexdigest(), duration_s=time.monotonic() - started,
        requested_duration_s=seconds, started_utc_unix_s=started_unix,
        max_bytes=max_bytes, gps_utc_offset_s=gps_utc_offset_s,
        connections=connections, stop_reason=stop_reason, events=transport_events,
        measurement_origin="remote_receiver; no local receiver or RF observations",
        timing_sidecar=str(sidecar))
    report_path.write_text(json.dumps(report, indent=2, allow_nan=False), encoding="utf-8")
    return report
