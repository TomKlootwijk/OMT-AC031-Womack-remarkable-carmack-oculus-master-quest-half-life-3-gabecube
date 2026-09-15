"""RTCM framing, unavailable-observation, epoch and HTTP transport regressions."""
import importlib.util
import hashlib
import importlib.metadata
import json
import math
from pathlib import Path
import socket
import sys
import tempfile
import threading
import time
import unittest
from collections import Counter

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from live_rtcm import (Bits, CallbackFailure, ChunkedBody, RTCMDecoder, RTCMError, RANGE_MS, WEEK,
                       capture, crc24q, epoch_from_event, ephemeris_from_event,
                       frame, nearest_tow, redact_url)

REFERENCE = 2436 * WEEK + 164500
# Real LIENSS station/GPS navigation frames captured September 14, 2026.
STATION = bytes.fromhex("d300153ee000030a4e209277bfcab22fe20aa7af73af000086592f")
EPHEMERIS = bytes.fromhex("d3003d3fb7584040d629286e00003ee023942907dc342ec8da808a06b701dbe5b606bfa10d4ac8286efff6c62140cafff92711d7f5278a76729524ffa459eb0056a828")


class Writer:
    def __init__(self):
        self.value = ""

    def add(self, value, count):
        self.value += format(value & ((1 << count) - 1), f"0{count}b")
        return self

    def payload(self):
        bits = self.value + "0" * (-len(self.value) % 8)
        return int(bits, 2).to_bytes(len(bits) // 8, "big")


def msm(kind=1077, tow=164500000, more=0, prn=3, signal=2, fine=101,
        rough=72, cnr=700, station=42):
    w = Writer().add(kind, 12).add(station, 12).add(tow, 30).add(more, 1)
    for value, bits in [(0, 3), (0, 7), (0, 2), (0, 2), (0, 1), (0, 3),
                        (1 << (64 - prn), 64), (1 << (32 - signal), 32), (1, 1)]:
        w.add(value, bits)
    high, rate = kind % 10 in (6, 7), kind % 10 in (5, 7)
    w.add(rough, 8)
    if rate:
        w.add(0, 4)
    w.add(321, 10)
    if rate:
        w.add(-10, 14)
    w.add(fine, 20 if high else 15).add(-42, 24 if high else 22)
    w.add(3, 10 if high else 4).add(0, 1).add(cnr if high else 44, 10 if high else 6)
    if rate:
        w.add(200, 15)
    return frame(w.payload())


def legacy(tow=164500000, more=0, delta=71, raw_code=123456, ambiguity=72):
    w = Writer().add(1004, 12).add(42, 12).add(tow, 30).add(more, 1)
    w.add(1, 5).add(0, 1).add(0, 3)
    for value, width in [(3,6),(0,1),(raw_code,24),(-524288,20),(1,7),(ambiguity,8),
                         (180,8),(3,2),(delta,14),(-524288,20),(2,7),(160,8)]:
        w.add(value, width)
    return frame(w.payload())


def event_of(raw, kind):
    return next(e for e in RTCMDecoder(REFERENCE).feed(raw) if e["type"] == kind)


class RTCMTests(unittest.TestCase):
    def test_crc_independent_check_vector(self):
        self.assertEqual(crc24q(b"123456789"), 0xCDE703)
        self.assertEqual(crc24q(STATION[:-3]), int.from_bytes(STATION[-3:], "big"))

    def test_every_split_boundary(self):
        reference = event_of(STATION, "station")
        for split in range(len(STATION) + 1):
            decoder = RTCMDecoder(REFERENCE)
            events = decoder.feed(STATION[:split]) + decoder.feed(STATION[split:])
            self.assertEqual([e for e in events if e["type"] == "station"], [reference])
            self.assertEqual(decoder.finish(), [])

    def test_single_byte_chunks_noise_and_concatenation(self):
        decoder = RTCMDecoder(REFERENCE)
        events = []
        for byte in b"NTRIP headers\r\n\r\n" + STATION + EPHEMERIS + STATION:
            events += decoder.feed(bytes([byte]))
        self.assertEqual(sum(e["type"] == "station" for e in events), 2)
        self.assertEqual(sum(e["type"] == "ephemeris" for e in events), 1)
        self.assertEqual(decoder.finish(), [])

    def test_crc_recovery_and_truncated_reset(self):
        corrupted = bytearray(STATION)
        corrupted[-1] ^= 1
        decoder = RTCMDecoder(REFERENCE)
        events = decoder.feed(corrupted + STATION + STATION[:8])
        self.assertTrue(any(e["type"] == "crc_error" for e in events))
        self.assertEqual(sum(e["type"] == "station" for e in events), 1)
        self.assertEqual(decoder.reset()[0]["type"], "truncated")
        self.assertEqual(decoder.feed(STATION)[0]["type"], "station")

    def test_malformed_length_padding_and_header(self):
        for bad in [frame(STATION[3:-4]), frame(STATION[3:-3] + b"\0"),
                    frame(bytes([0x3e, 0xe0]))]:
            self.assertEqual(event_of(bad, "malformed")["type"], "malformed")
        events = RTCMDecoder(REFERENCE).feed(b"\xd3\xfc\x03" + STATION)
        self.assertTrue(any(e["type"] == "malformed_header" for e in events))
        self.assertTrue(any(e["type"] == "station" for e in events))

    def test_station_negative_38bit_and_separate_height(self):
        e = event_of(STATION, "station")
        self.assertEqual(e["ecef_arp_m"], [4426043.0455, -89429.1998, 4576296.6447])
        self.assertEqual(e["antenna_height_m"], 0.)

    def test_ephemeris_shared_units_and_week(self):
        e = event_of(EPHEMERIS, "ephemeris")
        ephem = ephemeris_from_event(e)
        self.assertEqual(ephem.week, 2436)
        self.assertEqual(ephem.prn, 29)
        self.assertEqual(ephem.toe, 1473458400.)
        self.assertAlmostEqual(ephem.m0, -.43083184491842985 * math.pi)
        self.assertEqual(ephem.iode, ephem.iodc & 255)

    def test_msm4_5_6_7_pseudorange_scales(self):
        for kind in (1074, 1075, 1076, 1077):
            e = event_of(msm(kind=kind), "observation_fragment")
            ob = e["observations"][0]
            expected = (72 + 321 / 1024 + 101 * 2**(-29 if kind % 10 > 5 else -24)) * RANGE_MS
            self.assertAlmostEqual(ob["pseudorange_m"], expected, places=7)
            self.assertEqual(ob["code"], "C1C")
            self.assertEqual(ob["cn0_dbhz"], 43.75 if kind % 10 > 5 else 44.)

    def test_unavailable_values_do_not_become_zero_ranges(self):
        for kind, invalid in [(1074, -16384), (1075, -16384), (1076, -524288), (1077, -524288)]:
            e = event_of(msm(kind=kind, fine=invalid), "epoch")
            self.assertIsNone(e["observations"][0]["pseudorange_m"])
            self.assertEqual(len(epoch_from_event(e).observations), 0)
        for raw in [msm(rough=255), msm(signal=1), msm(prn=33)]:
            self.assertIsNone(event_of(raw, "epoch")["observations"][0]["pseudorange_m"])

    def test_legacy_code_independent_of_missing_carrier_phase(self):
        e = event_of(legacy(delta=-8192), "epoch")
        self.assertAlmostEqual(e["observations"][0]["pseudorange_m"], 72 * RANGE_MS + 2469.12)
        self.assertIsNone(e["observations"][1]["pseudorange_m"])
        self.assertEqual(len(epoch_from_event(e).observations), 1)

    def test_zero_legacy_code_from_real_missing_signal_is_not_an_observation(self):
        e = event_of(legacy(delta=-8192, raw_code=0, ambiguity=0), "epoch")
        self.assertEqual(e["observations"][0]["status"], "nonpositive_pseudorange")
        self.assertIsNone(e["observations"][0]["pseudorange_m"])
        self.assertEqual(len(epoch_from_event(e).observations), 0)

    def test_gps_fragment_and_mixed_constellation_completion(self):
        decoder = RTCMDecoder(REFERENCE)
        self.assertFalse(any(e["type"] == "epoch" for e in decoder.feed(msm(more=1), REFERENCE)))
        # BeiDou epoch is 14 seconds behind GPS.
        events = decoder.feed(msm(kind=1127, tow=164486000), REFERENCE + .75)
        epoch = next(e for e in events if e["type"] == "epoch")
        self.assertEqual(epoch["fragment_message_types"], [1077, 1127])
        self.assertEqual(len(epoch_from_event(epoch).observations), 1)
        self.assertEqual(epoch["first_fragment_reception_gpst_s"], REFERENCE)
        self.assertEqual(epoch["terminal_reception_gpst_s"], REFERENCE + .75)
        self.assertEqual(epoch["reception_gpst_s"], REFERENCE + .75)

    def test_truncated_nongps_cannot_terminate_gps(self):
        decoder = RTCMDecoder(REFERENCE)
        decoder.feed(msm(more=1))
        raw = msm(kind=1127, tow=164486000)
        events = decoder.feed(frame(raw[3:-4]))
        self.assertTrue(any(e["type"] == "malformed" for e in events))
        self.assertFalse(any(e["type"] == "epoch" for e in events))

    def test_changed_epoch_or_reconnect_abandons_pending(self):
        decoder = RTCMDecoder(REFERENCE)
        decoder.feed(msm(more=1))
        events = decoder.feed(msm(tow=164501000))
        self.assertTrue(any(e["type"] == "incomplete_epoch" for e in events))
        self.assertEqual(sum(e["type"] == "epoch" for e in events), 1)
        decoder.feed(msm(tow=164502000, more=1))
        self.assertEqual(decoder.reset()[0]["type"], "incomplete_epoch")

    def test_duplicate_and_conflicting_sequence(self):
        decoder = RTCMDecoder(REFERENCE)
        decoder.feed(msm())
        self.assertTrue(any(e["type"] == "stale_epoch" for e in decoder.feed(msm())))
        decoder = RTCMDecoder(REFERENCE)
        decoder.feed(msm(more=1))
        events = decoder.feed(msm(fine=102))
        self.assertEqual(events[-1]["type"], "incomplete_epoch")
        self.assertEqual(events[-1]["reason"], "conflicting_signal_fragments")

    def test_code_selection_prefers_resolution(self):
        decoder = RTCMDecoder(REFERENCE)
        events = decoder.feed(legacy(more=1) + msm())
        e = next(e for e in events if e["type"] == "epoch")
        selected = epoch_from_event(e)
        self.assertEqual(selected.source_metadata["selected_signals"][0]["signal_id"], 2)

    def test_week_and_glonass_day_rollover(self):
        self.assertEqual(nearest_tow(1., 2436 * WEEK + WEEK - 1), 2437 * WEEK + 1)
        self.assertEqual(nearest_tow(WEEK - 1, 2436 * WEEK + 1), 2436 * WEEK - 1)
        # GPS tow164500 -> GLONASS Sunday-based day2 at259? encode exact UTC+3.
        glot = 164500 + 10800 - 18
        day = int(glot // 86400)
        rawtime = (day << 27) | int((glot % 86400) * 1000)
        frag = event_of(msm(kind=1087, tow=rawtime), "observation_fragment")
        self.assertEqual(frag["time_gpst_s"], REFERENCE)
        with self.assertRaises(RTCMError):
            nearest_tow(WEEK, REFERENCE)

    @unittest.skipUnless(importlib.util.find_spec("pyrtcm"), "optional independent pyrtcm unavailable")
    def test_independent_pyrtcm_real_frames_and_all_msm_code_types(self):
        from pyrtcm import RTCMReader
        st = RTCMReader.parse(STATION)
        self.assertEqual(event_of(STATION, "station")["ecef_arp_m"], [st.DF025, st.DF026, st.DF027])
        ep = RTCMReader.parse(EPHEMERIS)
        ours = event_of(EPHEMERIS, "ephemeris")["ephemeris"]
        for key, field, factor in [("sqrt_a", "DF092", 1), ("m0", "DF088", math.pi),
            ("delta_n", "DF087", math.pi), ("af0", "DF084", 1), ("ecc", "DF090", 1),
            ("i0", "DF097", math.pi), ("omega_dot", "DF100", math.pi)]:
            self.assertEqual(ours[key], getattr(ep, field) * factor)
        for kind in (1074, 1075, 1076, 1077):
            for fine in (-500, 0, 201):
                raw = msm(kind=kind, fine=fine)
                other = RTCMReader.parse(raw)
                ob = event_of(raw, "epoch")["observations"][0]
                field = "DF405_01" if kind % 10 > 5 else "DF400_01"
                value = (other.DF397_01 + other.DF398_01 + getattr(other, field)) * RANGE_MS
                self.assertAlmostEqual(ob["pseudorange_m"], value, places=7)


class TransportTests(unittest.TestCase):
    def test_chunked_every_byte_extensions_and_trailers(self):
        parser = ChunkedBody()
        data = b"3;key=x\r\nabc\r\n2\r\nde\r\n0\r\nTest: yes\r\n\r\n"
        output = []
        for byte in data:
            output += parser.feed(bytes([byte]))
        parser.finish()
        self.assertEqual(b"".join(output), b"abcde")

    def test_chunked_malformed_and_truncated(self):
        for wire in (b"x\r\n", b"1\r\naXX", b"0\r\n\r\nx"):
            with self.assertRaises(RTCMError):
                ChunkedBody().feed(wire)
        parser = ChunkedBody()
        parser.feed(b"4\r\nab")
        with self.assertRaises(RTCMError):
            parser.finish()

    def serve(self, responses, tcp=False):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(2)
        server.settimeout(3)
        port = server.getsockname()[1]
        requests = []

        def run():
            try:
                for response in responses:
                    conn, _ = server.accept()
                    with conn:
                        if not tcp:
                            request = b""
                            while b"\r\n\r\n" not in request:
                                request += conn.recv(4096)
                            requests.append(request)
                        try:
                            for i in range(0, len(response), 7):
                                conn.sendall(response[i:i + 7])
                        except (ConnectionResetError, BrokenPipeError):
                            pass
            finally:
                server.close()
        thread = threading.Thread(target=run, daemon=True)
        thread.start()
        return port, thread, requests

    def test_http_chunked_capture_and_byte_provenance(self):
        response = b"HTTP/1.1 200 OK\r\nTransfer-Encoding: chunked\r\n\r\n" + hex(len(STATION))[2:].encode() + b"\r\n" + STATION + b"\r\n0\r\n\r\n"
        port, thread, requests = self.serve([response])
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "capture.rtcm3"
            pieces = []
            report = capture(f"http://name:secret@127.0.0.1:{port}/station", out,
                seconds=3, reconnects=0, on_chunk=lambda data, stamp: pieces.append(data))
            self.assertEqual(out.read_bytes(), STATION)
            self.assertEqual(b"".join(pieces), STATION)
            self.assertEqual(report["bytes"], len(STATION))
            self.assertNotIn("secret", json.dumps(report))
            self.assertNotIn("secret", Path(str(out) + ".timing.jsonl").read_text())
            with self.assertRaises(FileExistsError):
                capture(f"tcp://127.0.0.1:{port}", out)
        thread.join(3)
        self.assertIn(b"GET /station HTTP/1.1", requests[0])

    def test_icy_with_nonstandard_extra_headers(self):
        response = b"ICY 200 OK\r\nContent-Length: 0\r\nConnection: close\r\n\r\n" + STATION
        port, thread, _ = self.serve([response])
        with tempfile.TemporaryDirectory() as folder:
            events = []
            decoder = RTCMDecoder(REFERENCE)
            raw_path = Path(folder) / "raw"
            capture(f"ntrip://127.0.0.1:{port}/test", raw_path, seconds=3,
                reconnects=0, on_chunk=lambda data, stamp: events.extend(decoder.feed(data, stamp)))
            self.assertTrue(any(e["type"] == "station" for e in events))
            self.assertEqual(raw_path.read_bytes(), STATION)
        thread.join(3)

    def test_icy_direct_body_and_callback_error_propagation(self):
        port, thread, _ = self.serve([b"ICY 200 OK\r\n" + STATION])
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "raw"
            capture(f"ntrip://127.0.0.1:{port}/test", out, seconds=3, reconnects=0)
            self.assertEqual(out.read_bytes(), STATION)
        thread.join(3)
        port, thread, _ = self.serve([STATION], tcp=True)
        with tempfile.TemporaryDirectory() as folder:
            def failing_callback(data, stamp):
                raise ValueError("position model rejected supplied input")
            with self.assertRaises(CallbackFailure) as context:
                capture(f"tcp://127.0.0.1:{port}", Path(folder) / "raw", seconds=3,
                        reconnects=2, on_chunk=failing_callback)
            self.assertIsInstance(context.exception.__cause__, ValueError)
        thread.join(3)

    def test_idle_stream_timeout_obeys_capture_bound(self):
        server = socket.socket()
        server.bind(("127.0.0.1", 0))
        server.listen(1)
        port = server.getsockname()[1]
        def idle():
            conn, _ = server.accept()
            with conn:
                time.sleep(.15)
            server.close()
        thread = threading.Thread(target=idle, daemon=True)
        thread.start()
        with tempfile.TemporaryDirectory() as folder:
            started = time.monotonic()
            report = capture(f"tcp://127.0.0.1:{port}", Path(folder) / "raw",
                             seconds=.1, timeout=1, reconnects=0)
            self.assertLess(time.monotonic() - started, .6)
            self.assertEqual(report["bytes"], 0)
            self.assertEqual(report["stop_reason"], "duration_limit")
            self.assertFalse(any(e["type"] == "transport_error" for e in report["events"]))
        thread.join(3)

    def test_tcp_reconnect_boundary_and_bounded_capture(self):
        port, thread, _ = self.serve([STATION[:10], STATION * 10], tcp=True)
        with tempfile.TemporaryDirectory() as folder:
            out = Path(folder) / "capture"
            decoder = RTCMDecoder(REFERENCE)
            events = []

            def boundary(event):
                if event["type"] == "reconnecting":
                    events.extend(decoder.reset("transport_reconnect"))
            report = capture(f"tcp://127.0.0.1:{port}", out, seconds=3,
                max_bytes=10 + len(STATION), reconnects=1, on_event=boundary,
                on_chunk=lambda data, stamp: events.extend(decoder.feed(data, stamp)))
            self.assertEqual(report["bytes"], 10 + len(STATION))
            self.assertEqual(report["stop_reason"], "byte_limit")
            self.assertTrue(any(e["type"] == "truncated" for e in events))
            self.assertEqual(sum(e["type"] == "station" for e in events), 1)
        thread.join(3)


def audit_capture(path, reference_gpst_s, out):
    """Compare every supported field in a capture with independent pyrtcm code."""
    from pyrtcm import RTCMReader
    data = Path(path).read_bytes()
    decoder = RTCMDecoder(reference_gpst_s)
    events = []
    for offset in range(0, len(data), 127):
        events.extend(decoder.feed(data[offset:offset + 127]))
    ending = decoder.finish()
    comparisons = Counter()
    maxima = Counter()

    def equal(name, value, expected, tolerance=0.):
        comparisons[name] += 1
        if isinstance(expected, (int, float)) and not isinstance(expected, bool):
            error = abs(value - expected)
            maxima[name] = max(maxima[name], error)
            if error > tolerance:
                raise AssertionError(f"{name}: {value} versus {expected}")
        elif value != expected:
            raise AssertionError(f"{name}: {value} versus {expected}")

    for event in events:
        kind = event.get("message_type")
        if "raw_hex" not in event or kind not in (1004,1005,1006,1019,1074,1075,1076,1077):
            continue
        raw = bytes.fromhex(event["raw_hex"])
        decoded = RTCMReader.parse(raw)
        equal("message_type", kind, int(decoded.identity))
        if kind in (1005,1006):
            equal("station_id", event["station_id"], decoded.DF003)
            for axis, field in enumerate(("DF025", "DF026", "DF027")):
                equal("station_ecef_m", event["ecef_arp_m"][axis], getattr(decoded, field))
            if kind == 1006:
                equal("station_height_m", event["antenna_height_m"], decoded.DF028)
        elif kind == 1019:
            mappings = {"prn":"DF009", "iode":"DF071", "iodc":"DF085", "af0":"DF084",
                "af1":"DF083", "af2":"DF082", "crs":"DF086", "cuc":"DF089", "ecc":"DF090",
                "cus":"DF091", "sqrt_a":"DF092", "cic":"DF094", "cis":"DF096", "crc":"DF098",
                "tgd":"DF101", "health":"DF102"}
            for name, field in mappings.items():
                equal("ephemeris_scalar", event["ephemeris"][name], getattr(decoded, field))
            for name, field in {"idot":"DF079", "delta_n":"DF087", "m0":"DF088",
                                "omega0":"DF095", "i0":"DF097", "w":"DF099", "omega_dot":"DF100"}.items():
                equal("ephemeris_radians", event["ephemeris"][name], getattr(decoded, field) * math.pi)
            equal("ephemeris_week_mod", event["week_mod1024"], decoded.DF076)
            equal("ephemeris_toe_tow", event["ephemeris"]["toe"] % WEEK, decoded.DF093)
            equal("ephemeris_toc_tow", event["ephemeris"]["toc"] % WEEK, decoded.DF081)
        elif kind == 1004:
            for index, ob in enumerate(event["observations"]):
                suffix = f"_{index // 2 + 1:02d}"
                equal("legacy_prn", ob["prn"], getattr(decoded, "DF009" + suffix))
                if ob["pseudorange_m"] is not None:
                    pseudorange = getattr(decoded, "DF011" + suffix) + getattr(decoded, "DF014" + suffix) * RANGE_MS
                    if index % 2:
                        pseudorange += getattr(decoded, "DF017" + suffix)
                    equal("legacy_pseudorange_m", ob["pseudorange_m"], pseudorange, 1e-7)
                elif ob["status"] == "nonpositive_pseudorange":
                    pseudorange = getattr(decoded, "DF011" + suffix) + getattr(decoded, "DF014" + suffix) * RANGE_MS
                    if index % 2:
                        pseudorange += getattr(decoded, "DF017" + suffix)
                    equal("legacy_nonpositive_rejection", pseudorange <= 0, True)
                cnr = getattr(decoded, ("DF020" if index % 2 else "DF015") + suffix)
                equal("legacy_cn0_dbhz", ob["cn0_dbhz"], cnr if cnr else None)
        else:
            high = kind % 10 in (6,7)
            for index, ob in enumerate(event["observations"], 1):
                suffix = f"_{index:02d}"
                prn = int(getattr(decoded, "CELLPRN" + suffix))
                equal("msm_prn", ob["prn"], prn)
                equal("msm_code", ob["code"], "C" + getattr(decoded, "CELLSIG" + suffix))
                if ob["pseudorange_m"] is not None:
                    satellite_index = event["satellites"].index(prn) + 1
                    ss = f"_{satellite_index:02d}"
                    fine = getattr(decoded, ("DF405" if high else "DF400") + suffix)
                    pseudorange = (getattr(decoded, "DF397" + ss) + getattr(decoded, "DF398" + ss) + fine) * RANGE_MS
                    equal("msm_pseudorange_m", ob["pseudorange_m"], pseudorange, 1e-7)
                cnr = getattr(decoded, ("DF408" if high else "DF403") + suffix)
                equal("msm_cn0_dbhz", ob["cn0_dbhz"], cnr if cnr else None)
    errors = [e for e in events if e["type"] in ("malformed", "crc_error", "malformed_header")]
    if errors:
        raise AssertionError(f"capture parser errors: {len(errors)}")
    report = dict(status="passed", capture=str(path), capture_bytes=len(data),
        capture_sha256=hashlib.sha256(data).hexdigest(), reference_gpst_s=reference_gpst_s,
        parser_sha256=hashlib.sha256((Path(__file__).resolve().parents[1] / "python/live_rtcm.py").read_bytes()).hexdigest(),
        independent_library="pyrtcm", independent_version=importlib.metadata.version("pyrtcm"),
        comparisons=dict(comparisons), total_comparisons=sum(comparisons.values()),
        maximum_absolute_differences=dict(maxima), event_counts=dict(Counter(e["type"] for e in events)),
        message_counts=dict(decoder.counts), final_statuses=[dict(type=e["type"], reason=e.get("reason")) for e in ending],
        provenance="pyrtcm decodes identical independently CRC-validated rawframes; compares fields and range reconstruction, not position accuracy")
    Path(out).write_text(json.dumps(report, indent=2), encoding="utf-8")
    print(json.dumps(report, indent=2))


if __name__ == "__main__":
    if "--audit" in sys.argv:
        import argparse
        parser = argparse.ArgumentParser()
        parser.add_argument("--audit", required=True)
        parser.add_argument("--reference-gpst-s", type=float, required=True)
        parser.add_argument("--out", required=True)
        args = parser.parse_args()
        audit_capture(args.audit, args.reference_gpst_s, args.out)
    else:
        unittest.main()
