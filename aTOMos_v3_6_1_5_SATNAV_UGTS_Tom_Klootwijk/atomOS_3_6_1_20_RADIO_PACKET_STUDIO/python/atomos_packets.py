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
import re
import subprocess
import tempfile

DEFAULT_TSHARK = Path("C:/Program Files/Wireshark/tshark.exe")
FIELDS = ["frame.number", "frame.time_epoch", "frame.len", "frame.cap_len", "frame.protocols",
    "_ws.col.protocol", "eth.src", "eth.dst", "eth.type", "ip.src", "ip.dst", "ipv6.src", "ipv6.dst",
    "ip.proto", "ipv6.nxt", "tcp.stream", "tcp.srcport", "tcp.dstport", "tcp.flags", "tcp.seq", "tcp.ack",
    "tcp.analysis.retransmission", "udp.stream", "udp.srcport", "udp.dstport", "udp.length", "dns.id", "dns.flags.response",
    "dns.qry.name", "dns.qry.type", "dns.a", "dns.aaaa", "tls.record.content_type", "tls.record.opaque_type", "tls.handshake.type",
    "tls.handshake.extensions_server_name", "tls.handshake.extensions_alpn_str", "http.request.method",
    "http.host", "http.request.uri", "http.response.code", "http.content_type", "quic.version",
    "_ws.expert.message", "_ws.col.info"]
MAX_CAPTURE_BYTES = 64 * 1024 * 1024
UDP_PREVIEW_BYTES = 64
UDP_REPORT_RECORDS = 200


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


def udp_payload_previews(output: bytes, *, allowed_frames, preview_bytes=UDP_PREVIEW_BYTES):
    """Keep only a bounded preview of TShark's first UDP payload occurrence.

    The payload field may be reassembled by TShark; it is not a decryption.
    Original capture bytes, not this display, remain the lossless artifact.
    """
    reader = csv.DictReader(io.StringIO(output.decode("utf-8", errors="strict")))
    if reader.fieldnames != ["frame.number", "udp.payload"]:
        raise ValueError("UDP payload CSV header differs from declared fields")
    results = {}
    for row in reader:
        if None in row or any(value is None for value in row.values()):
            raise ValueError("malformed UDP payload CSV row")
        frame = row["frame.number"]
        if frame not in allowed_frames:
            continue
        occurrences = row["udp.payload"].split(";") if row["udp.payload"] else []
        if not occurrences:
            results[frame] = {"payload_available": False, "payload_occurrences": 0,
                              "hex_preview": "", "ascii_preview": "", "preview_bytes": 0,
                              "reported_payload_bytes": None, "preview_truncated": False}
            continue
        value = occurrences[0]
        if not re.fullmatch(r"[0-9a-fA-F:]*", value):
            raise ValueError("non-hexadecimal TShark UDP payload field")
        compact = value.replace(":", "")
        if len(compact) % 2:
            raise ValueError("odd-length TShark UDP payload field")
        preview = bytes.fromhex(compact[:2 * preview_bytes])
        results[frame] = {"payload_available": True, "payload_occurrences": len(occurrences),
            "hex_preview": preview.hex(" "),
            "ascii_preview": "".join(chr(byte) if 32 <= byte <= 126 else "." for byte in preview),
            "preview_bytes": len(preview), "reported_payload_bytes": len(compact) // 2,
            "preview_truncated": len(compact) // 2 > len(preview)}
    return results


def _udp_classification(row):
    protocols = set(row.get("frame.protocols", "").split(":"))
    if "quic" in protocols:
        return "QUIC transport: payload can be encrypted; this is a raw UDP-byte preview, not decrypted application content."
    if "dtls" in protocols:
        return "DTLS transport: encrypted or handshake records; raw UDP-byte preview only."
    upper = protocols - {"eth", "ethertype", "ip", "ipv6", "udp", "data", "raw", "sll", "vlan", "_ws.malformed"}
    if upper:
        return "TShark decoded: " + ", ".join(sorted(upper)) + ". Read the decoded fields alongside the raw-byte preview."
    return "Unknown or undissected UDP application payload. Binary bytes are not assumed to be plaintext."


def _endpoint(row, direction):
    addresses = [v for key in ("ip." + direction, "ipv6." + direction)
                 for v in row.get(key, "").split(";") if v]
    ports = [v for v in row.get("udp." + direction + "port", "").split(";") if v]
    if len(addresses) == len(ports) == 1:
        address = f"[{addresses[0]}]" if ":" in addresses[0] else addresses[0]
        return address + ":" + ports[0]
    return "addresses=" + json.dumps(addresses) + "; UDP ports=" + json.dumps(ports) + " (layer pairing not inferred)"


def write_udp_report(rows, previews, output: Path, *, label=None):
    udp_rows = [row for row in rows if row.get("udp.srcport") or row.get("udp.dstport")]
    selected = udp_rows[:UDP_REPORT_RECORDS]
    entries = []
    lines = ["# Readable UDP packet study", "", "Study label: " + (label or "not supplied"), "",
        f"Showing {len(selected)} of {len(udp_rows)} decoded UDP packet records. "
        f"At most {UDP_REPORT_RECORDS} records and {UDP_PREVIEW_BYTES} preview bytes per record are displayed.", "",
        "Times and protocol summaries come from the capture and TShark. The UDP length field includes its 8-byte header. "
        "Payloads may have been reassembled by TShark. Original captured bytes remain in the source artifact.", "",
        "Hex is the exact bounded byte preview. ASCII displays printable bytes and uses `.` for other bytes; "
        "printable characters do not establish plaintext. QUIC/DTLS bytes are not presented as decrypted application data.", ""]
    for row in selected:
        frame = row["frame.number"]
        preview = previews.get(frame, {"payload_available": False, "payload_occurrences": 0,
            "hex_preview": "", "ascii_preview": "", "preview_bytes": 0,
            "reported_payload_bytes": None, "preview_truncated": False})
        try:
            truncated_capture = int(row["frame.cap_len"]) < int(row["frame.len"])
        except (ValueError, KeyError):
            truncated_capture = None
        entry = {"frame": frame, "time_epoch_seconds": row.get("frame.time_epoch"),
            "source": _endpoint(row, "src"), "destination": _endpoint(row, "dst"),
            "udp_length_field": row.get("udp.length"), "captured_frame_bytes": row.get("frame.cap_len"),
            "original_frame_bytes": row.get("frame.len"), "captured_frame_truncated": truncated_capture,
            "protocol_stack": row.get("frame.protocols"), "decoded_summary": row.get("_ws.col.info"),
            "classification": _udp_classification(row), "dns_question": row.get("dns.qry.name"),
            "dns_a_answers": row.get("dns.a"), "dns_aaaa_answers": row.get("dns.aaaa"),
            "expert_messages": row.get("_ws.expert.message"), **preview}
        entries.append(entry)
        block = [f"Capture epoch time: {entry['time_epoch_seconds']}", f"Source: {entry['source']}",
            f"Destination: {entry['destination']}", f"UDP length field: {entry['udp_length_field']} bytes",
            f"Frame bytes captured/original: {entry['captured_frame_bytes']}/{entry['original_frame_bytes']}"
                + (" [CAPTURE TRUNCATED]" if truncated_capture else ""),
            f"Protocol stack: {entry['protocol_stack']}", f"Decoded summary: {entry['decoded_summary']}",
            "Classification: " + entry["classification"]]
        for key, title in (("dns_question", "DNS question"), ("dns_a_answers", "DNS A answers"),
                           ("dns_aaaa_answers", "DNS AAAA answers"), ("expert_messages", "Decoder messages")):
            if entry[key]:
                block.append(title + ": " + entry[key])
        if preview["payload_available"]:
            block += [f"First UDP payload preview: {preview['preview_bytes']} of {preview['reported_payload_bytes']} reported payload bytes; "
                      f"payload occurrences: {preview['payload_occurrences']}",
                      "HEX: " + preview["hex_preview"], "ASCII: " + preview["ascii_preview"]]
        else:
            block.append("UDP payload bytes unavailable or empty in this decoded record; nothing is invented.")
        body = "\n".join(block)
        fence = "`" * max(3, 1 + max((len(x) for x in re.findall(r"`+", body)), default=0))
        lines += [f"## UDP frame {frame}", "", fence + "text", body, fence, ""]
    metadata = {"profile": "atomos.udp-readable.v1", "decoded_udp_records": len(udp_rows),
        "displayed_records": len(selected), "omitted_records": max(0, len(udp_rows) - len(selected)),
        "preview_byte_limit": UDP_PREVIEW_BYTES, "record_limit": UDP_REPORT_RECORDS,
        "file": "udp_readable.md", "preview_json": "udp_previews.json"}
    (output / "udp_readable.md").write_text("\n".join(lines), encoding="utf-8")
    (output / "udp_previews.json").write_text(json.dumps({**metadata, "packets": entries}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return metadata


def markdown_report(summary):
    lines = ["# aTOMos R20 packet study", "", "Study label: " + (summary.get("study_label") or "not supplied"), "",
        f"Status: **{summary['status']}**. Capture: {summary['capture_format']}, {summary['input_bytes']} bytes.", "",
        f"Original SHA256: `{summary['input_sha256']}`.", "",
        f"Decoder: `{summary.get('tshark_version', 'unavailable')}`.", "",
        f"Decoded {summary['decoded_packet_rows']} packet rows; packet limit {summary['packet_limit']}; "
        f"limit reached: {summary['packet_limit_reached']}.", "",
        "All original bytes remain in `source_original." + (summary["capture_format"] if summary["capture_format"] != "unrecognized" else "bin") + "`. "
        "`packet_fields.csv` contains decoded metadata; `protocols_conversations.txt` contains TShark's protocol hierarchy and endpoint conversations.", "",
        "`udp_readable.md` shows decoded UDP summaries, endpoints and capped ASCII/hex payload previews. "
        "`udp_previews.json` keeps the same bounded structured view.", "",
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
    rows, udp_previews = [], {}
    with tempfile.TemporaryDirectory(prefix="atomos-tshark-config-") as config:
        env = os.environ.copy()
        env["WIRESHARK_CONFIG_DIR"] = config
        env.pop("SSLKEYLOGFILE", None)
        env.pop("TLSKEYLOGFILE", None)

        def invoke(name, args, *, retain_stdout=True):
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
            if retain_stdout:
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
            udp_frames = [row["frame.number"] for row in rows if row.get("udp.srcport") or row.get("udp.dstport")][:UDP_REPORT_RECORDS]
            if udp_frames:
                # Bound the extraction to the selected frames. Full UDP payload
                # field output is transient; only capped previews are retained.
                display_filter = "udp && frame.number <= " + str(max(int(frame) for frame in udp_frames))
                udp_status, udp_data = invoke("tshark_udp_payloads", base + ["-Y", display_filter,
                    "-T", "fields", "-E", "header=y", "-E", "separator=,", "-E", "quote=d",
                    "-E", "occurrence=a", "-E", "aggregator=;", "-e", "frame.number", "-e", "udp.payload"], retain_stdout=False)
                try:
                    udp_previews = udp_payload_previews(udp_data, allowed_frames=set(udp_frames))
                except (UnicodeDecodeError, ValueError, csv.Error) as error:
                    summary["decoder_errors"].append({"command": "parse_udp_payloads", "error": str(error)})
            summary["packet_limit_reached"] = len(rows) >= packet_limit
            if not summary["decoder_errors"] and fields_status == stats_status == 0:
                summary["status"] = "packet_limit_reached" if summary["packet_limit_reached"] else "decoded"
            elif rows:
                summary["status"] = "partial_decode_with_errors"
    summary.update(summarize_rows(rows))
    summary["udp_readable"] = write_udp_report(rows, udp_previews, output, label=label)
    (output / "summary.json").write_text(json.dumps(summary, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    (output / "summary.md").write_text(markdown_report(summary), encoding="utf-8")
    return summary
