from pathlib import Path
import csv
from decimal import Decimal
import hashlib
import io
import json
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "python"))
from atomos_packets import (DEFAULT_TSHARK, FIELDS, UDP_REPORT_RECORDS, capture_format, study_capture,
                            summarize_rows, udp_payload_previews, write_udp_report)

FIXTURES = Path(__file__).resolve().parents[1] / "examples/packets"


class PacketPolicyTests(unittest.TestCase):
    def test_format_recognition_both_endian_and_nanosecond_variants(self):
        for magic in ("d4c3b2a1", "a1b2c3d4", "4d3cb2a1", "a1b23c4d"):
            self.assertEqual(capture_format(bytes.fromhex(magic)), "pcap")
        self.assertEqual(capture_format(bytes.fromhex("0a0d0d0a")), "pcapng")
        self.assertEqual(capture_format(b"not capture"), "unrecognized")

    def test_error_status_and_partial_stdout_preserved(self):
        header = (",".join(FIELDS) + "\n").encode()
        def fake(command, *, env, timeout):
            self.assertIsInstance(command, list)
            self.assertNotIn("SSLKEYLOGFILE", env)
            if "--version" in command:
                return subprocess.CompletedProcess(command, 0, b"TShark test\n", b"")
            self.assertIn("-n", command)
            self.assertIn("-r", command)
            self.assertNotIn("-i", command)
            return subprocess.CompletedProcess(command, 2, header if "-T" in command else b"partial statistics", b"bad capture")
        with tempfile.TemporaryDirectory() as d, patch("atomos_packets._run", side_effect=fake):
            output = Path(d) / "out"
            summary = study_capture(FIXTURES / "synthetic_ethernet.pcap", output)
            self.assertEqual(summary["status"], "decode_failed")
            self.assertEqual(len(summary["decoder_errors"]), 2)
            self.assertEqual((output / "tshark_fields.stderr.txt").read_bytes(), b"bad capture")
            self.assertEqual((output / "protocols_conversations.txt").read_bytes(), b"partial statistics")

    def test_missing_executable_preserves_original_and_reports_failure(self):
        with tempfile.TemporaryDirectory() as d:
            output = Path(d) / "out"
            source = FIXTURES / "synthetic_ethernet.pcap"
            summary = study_capture(source, output, tshark=Path(d) / "missing.exe")
            self.assertEqual(summary["status"], "decode_failed")
            self.assertEqual((output / "source_original.pcap").read_bytes(), source.read_bytes())
            self.assertEqual(summary["decoder_errors"][0]["error"], "executable_error")

    def test_timeout_is_recorded_and_no_success_fabricated(self):
        with tempfile.TemporaryDirectory() as d, patch("atomos_packets._run", side_effect=subprocess.TimeoutExpired("tshark", 1)):
            summary = study_capture(FIXTURES / "synthetic_ethernet.pcap", Path(d) / "out")
            self.assertEqual(summary["status"], "decode_failed")
            self.assertEqual(summary["decoder_errors"][0]["error"], "timeout")

    def test_nonempty_output_and_input_resource_limit_refused(self):
        with tempfile.TemporaryDirectory() as d:
            directory = Path(d)
            (directory / "keep").write_bytes(b"existing")
            with self.assertRaisesRegex(ValueError, "empty directory"):
                study_capture(FIXTURES / "synthetic_ethernet.pcap", directory)
            with self.assertRaisesRegex(ValueError, "byte limit"):
                study_capture(FIXTURES / "synthetic_ethernet.pcap", directory / "new", max_capture_bytes=1)
            self.assertEqual((directory / "keep").read_bytes(), b"existing")
            self.assertFalse((directory / "new").exists())

    def test_path_metacharacters_stay_one_literal_argument(self):
        calls = []
        def fake(command, *, env, timeout):
            calls.append(command)
            return subprocess.CompletedProcess(command, 0, b"TShark test\n" if "--version" in command else
                ((",".join(FIELDS) + "\n").encode() if "-T" in command else b""), b"")
        with tempfile.TemporaryDirectory() as d, patch("atomos_packets._run", side_effect=fake):
            root = Path(d)
            source = root / "capture; & quoted ' data.pcap"
            source.write_bytes((FIXTURES / "synthetic_ethernet.pcap").read_bytes())
            output = root / "output; & quoted ' data"
            result = study_capture(source, output)
            self.assertEqual(result["status"], "decoded")
            for args in calls[1:]:
                self.assertEqual(args[args.index("-r") + 1], str((output / "source_original.pcap").resolve()))

    def test_partial_csv_rows_do_not_silently_become_full_observations(self):
        def fake(command, *, env, timeout):
            return subprocess.CompletedProcess(command, 0, b"TShark test\n" if "--version" in command else
                ((",".join(FIELDS) + "\n1,2\n").encode() if "-T" in command else b""), b"")
        with tempfile.TemporaryDirectory() as d, patch("atomos_packets._run", side_effect=fake):
            summary = study_capture(FIXTURES / "synthetic_ethernet.pcap", Path(d) / "out")
            self.assertEqual(summary["decoded_packet_rows"], 0)
            self.assertEqual(summary["status"], "decode_failed")

    def test_tls13_outer_application_data_is_counted_without_claiming_inner_plaintext(self):
        result = summarize_rows([{"frame.number": "1", "frame.protocols": "ip:tcp:tls",
            "frame.time_epoch": "1700000000.0", "frame.len": "100", "frame.cap_len": "100",
            "tls.record.content_type": "", "tls.record.opaque_type": "23"}])
        self.assertEqual(result["tls_application_data_record_frame_numbers"], ["1"])

    def test_udp_binary_preview_is_exact_bounded_and_not_assumed_plaintext(self):
        body = bytes(range(256))
        raw = ("frame.number,udp.payload\n1," + body.hex(":") + "\n").encode()
        previews = udp_payload_previews(raw, allowed_frames={"1"})
        p = previews["1"]
        self.assertEqual(p["reported_payload_bytes"], 256)
        self.assertEqual(p["preview_bytes"], 64)
        self.assertEqual(bytes.fromhex(p["hex_preview"]), body[:64])
        self.assertTrue(p["preview_truncated"])
        row = {"frame.number": "1", "frame.protocols": "ip:udp:data", "ip.src": "192.0.2.10",
               "ip.dst": "192.0.2.20", "udp.srcport": "5000", "udp.dstport": "5001",
               "udp.length": "264", "frame.cap_len": "284", "frame.len": "284"}
        with tempfile.TemporaryDirectory() as d:
            write_udp_report([row], previews, Path(d), label="SYNTHETIC")
            report = (Path(d) / "udp_readable.md").read_text()
            self.assertIn("192.0.2.10:5000", report)
            self.assertIn("Unknown or undissected UDP", report)
            self.assertIn("64 of 256", report)
            self.assertIn("Binary bytes are not assumed to be plaintext", report)

    def test_udp_report_record_bound_and_ipv6_addresses(self):
        rows = [{"frame.number": str(i), "frame.protocols": "ipv6:udp:quic",
                 "ipv6.src": "2001:db8::1", "ipv6.dst": "2001:db8::2",
                 "udp.srcport": "55000", "udp.dstport": "443"} for i in range(UDP_REPORT_RECORDS + 1)]
        with tempfile.TemporaryDirectory() as d:
            meta = write_udp_report(rows, {}, Path(d))
            self.assertEqual(meta["displayed_records"], 200)
            self.assertEqual(meta["omitted_records"], 1)
            report = (Path(d) / "udp_readable.md").read_text()
            self.assertIn("[2001:db8::1]:55000", report)
            self.assertIn("QUIC transport", report)
            self.assertIn("not decrypted application content", report)

    def test_udp_payload_parser_rejects_bad_hex_and_does_not_invent_bytes(self):
        for invalid in (b"frame.number,udp.payload\n1,abc\n", b"frame.number,udp.payload\n1,zz\n"):
            with self.assertRaises(ValueError):
                udp_payload_previews(invalid, allowed_frames={"1"})


@unittest.skipUnless(DEFAULT_TSHARK.is_file(), "Local official TShark is unavailable")
class TsharkIntegrationTests(unittest.TestCase):
    def study(self, name, **options):
        temporary = tempfile.TemporaryDirectory()
        self.addCleanup(temporary.cleanup)
        output = Path(temporary.name) / "study"
        result = study_capture(FIXTURES / name, output, label="SYNTHETIC TEST", **options)
        rows = list(csv.DictReader(io.StringIO((output / "packet_fields.csv").read_text(encoding="utf-8")))) if (output / "packet_fields.csv").exists() else []
        return result, rows, output

    def test_protocol_fixture_and_pcapng_have_matching_decoded_fields(self):
        first, rows, output = self.study("synthetic_ethernet.pcap")
        second, other, _ = self.study("synthetic_ethernet.pcapng")
        self.assertEqual(first["status"], "decoded")
        self.assertEqual(first["decoded_packet_rows"], 17)
        self.assertEqual(first["dns_query_names"], ["example.test"])
        self.assertEqual(first["tls_sni_names"], ["example.test"])
        self.assertEqual(first["http_request_methods"], {"GET": 1})
        self.assertEqual(first["http_response_codes"], {"200": 1})
        self.assertEqual(first["tls_application_data_record_frame_numbers"], ["12"])
        self.assertEqual(first["truncated_captured_frame_numbers"], ["17"])
        for field in ("frame.protocols", "frame.time_epoch", "frame.cap_len", "dns.qry.name", "tls.handshake.extensions_server_name"):
            self.assertEqual([r[field] for r in rows], [r[field] for r in other])
        source = (FIXTURES / "synthetic_ethernet.pcap").read_bytes()
        self.assertEqual((output / "source_original.pcap").read_bytes(), source)
        self.assertEqual(first["input_sha256"], hashlib.sha256(source).hexdigest())
        statistics = (output / "protocols_conversations.txt").read_text()
        self.assertIn("Protocol Hierarchy Statistics", statistics)
        self.assertIn("TCP Conversations", statistics)
        readable = (output / "udp_readable.md").read_text()
        self.assertIn("DNS question: example.test", readable)
        self.assertIn("DNS A answers: 203.0.113.7", readable)
        self.assertIn("Source: 192.0.2.10:53000", readable)
        self.assertEqual(first["udp_readable"]["decoded_udp_records"], 4)

    def test_mixed_endian_sections_interfaces_resolution_and_offset(self):
        summary, rows, _ = self.study("synthetic_mixed_sections.pcapng")
        self.assertEqual(summary["status"], "decoded")
        self.assertEqual([Decimal(r["frame.time_epoch"]) for r in rows],
            [Decimal("1700000000.25"), Decimal("1700000000.5"), Decimal("1700000000.75")])
        self.assertTrue(all(r["dns.qry.name"] == "example.test" for r in rows))

    def test_raw_big_endian_nanoseconds_and_linux_cooked(self):
        summary, rows, _ = self.study("synthetic_raw_be_ns.pcap")
        self.assertEqual(summary["status"], "decoded")
        self.assertEqual(rows[0]["frame.time_epoch"], "1700000000.123456789")
        self.assertEqual(rows[0]["dns.qry.name"], "example.test")
        _, cooked, _ = self.study("synthetic_sll.pcap")
        self.assertEqual(cooked[0]["dns.qry.name"], "example.test")

    def test_malformed_dns_is_exposed_not_repaired(self):
        summary, rows, _ = self.study("synthetic_dns_pointer_loop.pcap")
        self.assertEqual(summary["decoded_packet_rows"], 1)
        self.assertTrue(summary["malformed_frame_numbers"] or rows[0]["_ws.expert.message"] or summary["dns_name_decode_diagnostics"])
        self.assertNotIn("example.test", summary["dns_query_names"])

    def test_invalid_containers_report_decoder_error_and_keep_partial_rows(self):
        for name in ("invalid_unknown_interface.pcapng", "invalid_truncated_file.pcap", "invalid_not_capture.pcap"):
            with self.subTest(name=name):
                summary, rows, output = self.study(name)
                self.assertNotEqual(summary["status"], "decoded")
                self.assertTrue(summary["decoder_errors"])
                self.assertEqual(summary["input_sha256"], hashlib.sha256((FIXTURES / name).read_bytes()).hexdigest())
                if "truncated_file" in name:
                    self.assertGreater(len(rows), 0)
                    self.assertEqual(summary["status"], "partial_decode_with_errors")

    def test_packet_limit_does_not_claim_complete_file_analysis(self):
        summary, rows, _ = self.study("synthetic_ethernet.pcap", packet_limit=3)
        self.assertEqual(len(rows), 3)
        self.assertTrue(summary["packet_limit_reached"])
        self.assertEqual(summary["status"], "packet_limit_reached")

    def test_truncated_udp_reports_actual_preview_and_declared_length(self):
        summary, rows, output = self.study("synthetic_udp_truncated.pcap")
        self.assertEqual(summary["status"], "decoded")
        self.assertEqual(summary["truncated_captured_frame_numbers"], ["1"])
        preview = json.loads((output / "udp_previews.json").read_text())["packets"][0]
        self.assertTrue(preview["captured_frame_truncated"])
        self.assertEqual(preview["reported_payload_bytes"], 4)
        self.assertEqual(preview["hex_preview"], "54 52 55 4e")
        self.assertGreater(int(preview["udp_length_field"]) - 8, preview["reported_payload_bytes"])
        self.assertIn("[CAPTURE TRUNCATED]", (output / "udp_readable.md").read_text())


if __name__ == "__main__":
    unittest.main()
