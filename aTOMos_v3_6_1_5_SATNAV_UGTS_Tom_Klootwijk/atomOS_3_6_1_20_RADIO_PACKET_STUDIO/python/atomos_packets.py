"""Offline PCAP/PCAPNG metadata study using the installed TShark dissectors.

Calls use argv arrays, -n, a private empty configuration directory and no live
capture interface. The original capture is copied unchanged before decoding.
"""
from __future__ import annotations

from collections import Counter
import csv
from decimal import Decimal, InvalidOperation
import hashlib
import io
import json
import os
from pathlib import Path
import subprocess
import tempfile

DEFAULT_TSHARK = Path("C:/Program Files/Wireshark/tshark.exe")
FIELDS = ["frame.number", "frame.time_epoch", "frame.len", "frame.cap_len", "frame.protocols",
    "_ws.col.protocol", "eth.src", "eth.dst", "eth.type", "ip.src", "ip.dst", "ipv6.src", "ipv6.dst",
    "ip.proto", "ipv6.nxt", "tcp.stream", "tcp.srcport", "tcp.dstport", "tcp.flags", "tcp.seq", "tcp.ack",
    "tcp.analysis.retransmission", "udp.stream", "udp.srcport", "udp.dstport", "dns.id", "dns.flags.response",
    "dns.qry.name", "dns.qry.type", "dns.a", "dns.aaaa", "tls.record.content_type", "tls.record.opaque_type", "tls.handshake.type",
    "tls.handshake.extensions_server_name", "tls.handshake.extensions_alpn_str", "http.request.method",
    "http.host", "http.request.uri", "http.response.code", "http.content_type", "quic.version",
    "_ws.expert.message", "_ws.col.info"]
MAX_CAPTURE_BYTES = 64 * 1024 * 1024


def _run(arguments, *, env, timeout):
    return subprocess.run(arguments, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                          shell=False, env=env, timeout=timeout, check=False)


def capture_format(data: bytes):
    if data[:4] == bytes.fromhex("0a0d0d0a"):
        return "pcapng"
    if data[:4] in (bytes.fromhex(x) for x in ("d4c3b2a1", "a1b2c3d4", "4d3cb2a1", "a1b23c4d")):
        return "pcap"
    return "unrecognized"


def _values(rows, field):
    return [value for row in rows for value in row.get(field, "").split(";") if value]


def summarize_rows(rows):
    protocols = Counter()
    malformed, truncated, opaque_tls, dns_diagnostics = [], [], [], []
    times = []
    lengths = []
    for row in rows:
        names = set(row.get("frame.protocols", "").split(":")) - {""}
        protocols.update(names)
        number = row.get("frame.number")
        if "_ws.malformed" in names:
            malformed.append(number)
        try:
            if int(row["frame.cap_len"]) < int(row["frame.len"]):
                truncated.append(number)
            lengths.append(int(row["frame.cap_len"]))
        except (ValueError, KeyError):
            pass
        if "23" in (row.get("tls.record.content_type", "") + ";" + row.get("tls.record.opaque_type", "")).split(";"):
            opaque_tls.append(number)
        if "<Name contains a pointer that loops>" in row.get("dns.qry.name", ""):
            dns_diagnostics.append({"frame": number, "diagnostic": "TShark reports a DNS compression pointer loop"})
        try:
            timestamp = Decimal(row["frame.time_epoch"])
            if timestamp.is_finite():
                times.append(timestamp)
        except (InvalidOperation, KeyError):
            pass
    return {"decoded_packet_rows": len(rows), "protocol_frame_counts": dict(sorted(protocols.items())),
        "captured_packet_bytes": sum(lengths),
        "first_epoch_seconds": str(min(times)) if times else None,
        "last_epoch_seconds": str(max(times)) if times else None,
        "covered_seconds": str(max(times) - min(times)) if times else None,
        "truncated_captured_frame_numbers": truncated, "malformed_frame_numbers": malformed,
        "tls_application_data_record_frame_numbers": opaque_tls,
        "dns_name_decode_diagnostics": dns_diagnostics,
        "dns_query_names": sorted(set(_values(rows, "dns.qry.name")) - {"<Name contains a pointer that loops>"}),
        "tls_sni_names": sorted(set(_values(rows, "tls.handshake.extensions_server_name"))),
        "http_request_methods": dict(Counter(_values(rows, "http.request.method"))),
        "http_response_codes": dict(Counter(_values(rows, "http.response.code"))),
        "tcp_retransmission_marked_frames": [r.get("frame.number") for r in rows if r.get("tcp.analysis.retransmission")],
        "ipv4_endpoints": sorted(set(_values(rows, "ip.src") + _values(rows, "ip.dst"))),
        "ipv6_endpoints": sorted(set(_values(rows, "ipv6.src") + _values(rows, "ipv6.dst"))),
        "visibility": "Fields decoded from captured bytes by TShark. TLS application-data records and QUIC may carry encrypted payloads; metadata is not plaintext content. No keys or decryption service are supplied. A PCAPNG file can itself contain embedded decryption secrets; any resulting dissection is attributed to the input and TShark, not invented by this tool.",
        "scope": "Offline capture only. Protocol counts may overlap because one frame contains multiple protocol layers. Captured IP traffic is not a radio-power observation or arbitrary neighboring subscriber traffic."}


def markdown_report(summary):
    lines = ["# aTOMos R20 packet study", "", "Study label: " + (summary.get("study_label") or "not supplied"), "",
        f"Status: **{summary['status']}**. Capture: {summary['capture_format']}, {summary['input_bytes']} bytes.", "",
        f"Original SHA256: `{summary['input_sha256']}`.", "",
        f"Decoder: `{summary.get('tshark_version', 'unavailable')}`.", "",
        f"Decoded {summary['decoded_packet_rows']} packet rows; packet limit {summary['packet_limit']}; "
        f"limit reached: {summary['packet_limit_reached']}.", "",
        "All original bytes remain in `source_original." + (summary["capture_format"] if summary["capture_format"] != "unrecognized" else "bin") + "`. "
        "`packet_fields.csv` contains decoded metadata; `protocols_conversations.txt` contains TShark's protocol hierarchy and endpoint conversations.", "",
        "## Protocols", "", "| Protocol | Frames containing layer |", "|---|---:|"]
    lines.extend(f"| {name} | {count} |" for name, count in summary["protocol_frame_counts"].items())
    lines += ["", "## Capture interpretation", "", summary["scope"], "", summary["visibility"], "",
        "Captured-frame truncations: " + ", ".join(summary["truncated_captured_frame_numbers"] or ["none detected"]),
        "", "Malformed dissections: " + ", ".join(summary["malformed_frame_numbers"] or ["none detected"]), "",
        "DNS name decoder diagnostics: " + json.dumps(summary["dns_name_decode_diagnostics"], ensure_ascii=False), "",
        "TLS application-data record frames: " + ", ".join(summary["tls_application_data_record_frame_numbers"] or ["none decoded"]), "",
        "That count includes TLS 1.3 opaque outer record type 23; it does not identify the encrypted inner content type.", "",
        "## Decoded names and HTTP metadata", "", "These are values in packet bytes, not DNS/network lookups performed during analysis.", ""]
    for key in ("dns_query_names", "tls_sni_names", "http_request_methods", "http_response_codes"):
        lines.append(f"- {key}: `{json.dumps(summary[key], ensure_ascii=False)}`")
    lines += ["", "## Decoder issues", ""]
    lines.extend("- " + json.dumps(error, ensure_ascii=False) for error in summary["decoder_errors"])
    if not summary["decoder_errors"]:
        lines.append("No command errors. Frame-level expert messages remain in `packet_fields.csv`.")
    lines += ["", "Absolute capture times are source-provided; this report does not establish synchronization with another device or radio log.", ""]
    return "\n".join(lines)


def study_capture(source: Path, output: Path, *, tshark=DEFAULT_TSHARK, label=None,
                  packet_limit=100_000, timeout_seconds=45, max_capture_bytes=MAX_CAPTURE_BYTES):
    source, output, tshark = Path(source), Path(output), Path(tshark)
    if type(packet_limit) is not int or not 1 <= packet_limit <= 1_000_000:
        raise ValueError("packet_limit must be an integer in 1..1000000")
    if timeout_seconds <= 0 or timeout_seconds > 300:
        raise ValueError("timeout_seconds must be in (0,300]")
    if output.exists() and (not output.is_dir() or any(output.iterdir())):
        raise ValueError("packet output must be a new or empty directory")
    if not source.is_file():
        raise ValueError("capture input must be a file")
    if source.stat().st_size > max_capture_bytes:
        raise ValueError("capture exceeds the declared input byte limit")
    raw = source.read_bytes()
    fmt = capture_format(raw)
    destination = output / ("source_original." + (fmt if fmt != "unrecognized" else "bin"))
    if source.resolve() == destination.resolve():
        raise ValueError("packet output would overwrite input")
    output.mkdir(parents=True, exist_ok=True)
    destination.write_bytes(raw)
    summary = {"schema": "atomos.packet.study.v1", "study_label": label,
        "input_sha256": hashlib.sha256(raw).hexdigest(), "input_bytes": len(raw),
        "capture_format": fmt, "packet_limit": packet_limit, "max_capture_bytes": max_capture_bytes,
        "packet_limit_reached": False, "status": "decode_failed", "decoder_errors": [],
        "commands": [], "network_lookups": False, "subprocess_shell": False,
        "configuration": "Temporary empty Wireshark configuration; SSLKEYLOGFILE removed; tls.keylog_file cleared. Embedded capture metadata remains input data."}
    rows = []
    with tempfile.TemporaryDirectory(prefix="atomos-tshark-config-") as config:
        env = os.environ.copy()
        env["WIRESHARK_CONFIG_DIR"] = config
        env.pop("SSLKEYLOGFILE", None)
        env.pop("TLSKEYLOGFILE", None)

        def invoke(name, args):
            command = [str(tshark.resolve()), *args]
            summary["commands"].append({"name": name, "argv": command})
            try:
                result = _run(command, env=env, timeout=timeout_seconds)
                stdout, stderr = result.stdout, result.stderr
                code = result.returncode
            except subprocess.TimeoutExpired as error:
                stdout, stderr, code = error.stdout or b"", error.stderr or b"", None
                summary["decoder_errors"].append({"command": name, "error": "timeout", "seconds": timeout_seconds})
            except OSError as error:
                stdout, stderr, code = b"", str(error).encode("utf-8"), None
                summary["decoder_errors"].append({"command": name, "error": "executable_error", "message": str(error)})
            (output / (name + ".stdout.txt")).write_bytes(stdout)
            (output / (name + ".stderr.txt")).write_bytes(stderr)
            if code not in (0, None):
                summary["decoder_errors"].append({"command": name, "exit_code": code,
                    "stderr": stderr.decode("utf-8", errors="replace")})
            return code, stdout

        version_status, version = invoke("tshark_version", ["--version"])
        summary["tshark_version"] = version.decode("utf-8", errors="replace").splitlines()[0] if version else None
        if version_status == 0:
            base = ["-n", "-o", "tls.keylog_file:", "-r", str(destination.resolve()), "-c", str(packet_limit)]
            field_args = ["-T", "fields", "-E", "header=y", "-E", "separator=,", "-E", "quote=d",
                          "-E", "occurrence=a", "-E", "aggregator=;"]
            for field in FIELDS:
                field_args += ["-e", field]
            fields_status, fields = invoke("tshark_fields", base + field_args)
            (output / "packet_fields.csv").write_bytes(fields)
            try:
                reader = csv.DictReader(io.StringIO(fields.decode("utf-8", errors="strict")))
                if reader.fieldnames != FIELDS:
                    raise ValueError("TShark CSV header does not match the declared fields")
                for row in reader:
                    if None in row or any(v is None for v in row.values()):
                        raise ValueError("incomplete or malformed TShark CSV row")
                    rows.append(row)
            except (UnicodeDecodeError, ValueError, csv.Error) as error:
                summary["decoder_errors"].append({"command": "parse_fields", "error": str(error)})
            stats_status, stats = invoke("tshark_statistics", base + ["-q", "-z", "io,phs",
                "-z", "conv,tcp", "-z", "conv,udp", "-z", "conv,ip", "-z", "conv,ipv6"])
            (output / "protocols_conversations.txt").write_bytes(stats)
            summary["packet_limit_reached"] = len(rows) >= packet_limit
            if not summary["decoder_errors"] and fields_status == stats_status == 0:
                summary["status"] = "packet_limit_reached" if summary["packet_limit_reached"] else "decoded"
            elif rows:
                summary["status"] = "partial_decode_with_errors"
    summary.update(summarize_rows(rows))
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "summary.md").write_text(markdown_report(summary), encoding="utf-8")
    return summary
