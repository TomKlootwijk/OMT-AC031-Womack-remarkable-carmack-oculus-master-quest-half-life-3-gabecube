"""Deterministic synthetic packet containers using documentation-only addresses.

No sockets or external traffic are used. Payloads are artificial test data.
The bytes exercise decoders, not an authenticated TLS connection.
"""
from pathlib import Path
import hashlib
import ipaddress
import json
import struct

ROOT = Path(__file__).resolve().parent
EPOCH = 1_700_000_000


def checksum(data):
    data += bytes(len(data) % 2)
    result = sum(struct.unpack("!" + "H" * (len(data) // 2), data))
    while result >> 16:
        result = (result & 65535) + (result >> 16)
    return (~result) & 65535


def ip4(payload, proto, src="192.0.2.10", dst="198.51.100.20", ident=1, fragment=0):
    a, b = ipaddress.ip_address(src).packed, ipaddress.ip_address(dst).packed
    header = struct.pack("!BBHHHBBH4s4s", 0x45, 0, 20 + len(payload), ident, fragment, 64, proto, 0, a, b)
    return header[:10] + struct.pack("!H", checksum(header)) + header[12:] + payload


def ip6(payload, proto, src="2001:db8:a::10", dst="2001:db8:b::53"):
    return struct.pack("!IHBB16s16s", 6 << 28, len(payload), proto, 64,
                       ipaddress.ip_address(src).packed, ipaddress.ip_address(dst).packed) + payload


def transport_checksum(payload, proto, src, dst):
    a, b = ipaddress.ip_address(src), ipaddress.ip_address(dst)
    pseudo = (a.packed + b.packed + struct.pack("!BBH", 0, proto, len(payload)) if a.version == 4
              else a.packed + b.packed + struct.pack("!I3xB", len(payload), proto))
    return checksum(pseudo + payload)


def udp(data, sport, dport, src, dst):
    body = struct.pack("!HHHH", sport, dport, len(data) + 8, 0) + data
    return body[:6] + struct.pack("!H", transport_checksum(body, 17, src, dst) or 65535) + body[8:]


def tcp(data, sport, dport, seq, ack, flags, src, dst):
    body = struct.pack("!HHIIBBHHH", sport, dport, seq, ack, 5 << 4, flags, 65535, 0, 0) + data
    return body[:16] + struct.pack("!H", transport_checksum(body, 6, src, dst)) + body[18:]


def ether(payload, kind=0x0800):
    return bytes.fromhex("021900000002021900000001") + struct.pack("!H", kind) + payload


def dns_name(name):
    return b"".join(bytes([len(label)]) + label.encode("ascii") for label in name.split(".")) + b"\0"


def query(qtype=1):
    return struct.pack("!6H", 0x1919, 0x0100, 1, 0, 0, 0) + dns_name("example.test") + struct.pack("!HH", qtype, 1)


def tls_hello():
    hostname = b"example.test"
    names = b"\0" + struct.pack("!H", len(hostname)) + hostname
    sni = struct.pack("!HHH", 0, len(names) + 2, len(names)) + names
    body = b"\x03\x03" + bytes(range(32)) + b"\0\0\x02\xc0\x2f\x01\0" + struct.pack("!H", len(sni)) + sni
    handshake = b"\x01" + len(body).to_bytes(3, "big") + body
    return b"\x16\x03\x01" + struct.pack("!H", len(handshake)) + handshake


def classic(packets, link=1, endian="<", nano=False):
    magic = 0xA1B23C4D if nano else 0xA1B2C3D4
    out = struct.pack(endian + "IHHIIII", magic, 2, 4, 0, 0, 262144, link)
    for i, (captured, wire) in enumerate(packets):
        fraction = 123456789 if nano else 100000 + i * 1000
        out += struct.pack(endian + "IIII", EPOCH + i, fraction, len(captured), wire) + captured
    return out


def ng_block(kind, body, endian="<"):
    body += bytes((-len(body)) % 4)
    length = len(body) + 12
    return struct.pack(endian + "II", kind, length) + body + struct.pack(endian + "I", length)


def section(endian="<"):
    return ng_block(0x0A0D0D0A, struct.pack(endian + "IHHq", 0x1A2B3C4D, 1, 0, -1), endian)


def interface(link, resolution=6, offset=0, endian="<"):
    options = struct.pack(endian + "HHB3x", 9, 1, resolution)
    options += struct.pack(endian + "HHq", 14, 8, offset) + bytes(4)
    return ng_block(1, struct.pack(endian + "HHI", link, 0, 262144) + options, endian)


def enhanced(packet, timestamp, interface_id=0, wire=None, endian="<"):
    body = struct.pack(endian + "IIIII", interface_id, timestamp >> 32, timestamp & 0xFFFFFFFF,
                       len(packet), len(packet) if wire is None else wire) + packet
    return ng_block(6, body, endian)


def build():
    packets, descriptions = [], []

    def add(description, packet, wire=None):
        packets.append((packet, len(packet) if wire is None else wire))
        descriptions.append(description)

    q = query()
    add("IPv4 UDP DNS question example.test A", ether(ip4(udp(q, 53000, 53, "192.0.2.10", "192.0.2.53"), 17, dst="192.0.2.53")))
    answer = struct.pack("!6H", 0x1919, 0x8180, 1, 1, 0, 0) + q[12:] + b"\xc0\x0c" + struct.pack("!HHIH", 1, 1, 60, 4) + ipaddress.ip_address("203.0.113.7").packed
    add("IPv4 UDP compressed DNS answer 203.0.113.7", ether(ip4(udp(answer, 53, 53000, "192.0.2.53", "192.0.2.10"), 17, src="192.0.2.53", dst="192.0.2.10")))
    for port, dport, label in ((40000, 80, "HTTP"), (40001, 443, "TLS")):
        for description, seq, ack, flags, reverse in (("SYN", 1000, 0, 2, False), ("SYN ACK", 2000, 1001, 18, True), ("ACK", 1001, 2001, 16, False)):
            src, dst = ("198.51.100.20", "192.0.2.10") if reverse else ("192.0.2.10", "198.51.100.20")
            sp, dp = (dport, port) if reverse else (port, dport)
            add(label + " TCP " + description, ether(ip4(tcp(b"", sp, dp, seq, ack, flags, src, dst), 6, src, dst)))
        data = b"GET /synthetic HTTP/1.1\r\nHost: example.test\r\nConnection: close\r\n\r\n" if label == "HTTP" else tls_hello()
        request_description = "HTTP GET /synthetic" if label == "HTTP" else "TLS ClientHello with SNI example.test"
        add(request_description, ether(ip4(tcp(data, port, dport, 1001, 2001, 24, "192.0.2.10", "198.51.100.20"), 6)))
        response = (b"HTTP/1.1 200 OK\r\nContent-Type: text/plain\r\nContent-Length: 10\r\n\r\nsynthetic\n" if label == "HTTP"
                    else b"\x17\x03\x03\0\x10" + bytes(range(16)))
        response_description = "HTTP 200 response" if label == "HTTP" else "TLS opaque application-data record (outer type 23)"
        add(response_description, ether(ip4(tcp(response, dport, port, 2001, 1001 + len(data), 24,
            "198.51.100.20", "192.0.2.10"), 6, "198.51.100.20", "192.0.2.10")))
    v6 = ip6(udp(query(28), 53001, 53, "2001:db8:a::10", "2001:db8:b::53"), 17)
    add("IPv6 UDP DNS AAAA question", ether(v6, 0x86DD))
    fragmented = udp(b"SYNTHETIC-FRAGMENT-" + bytes(24), 49000, 49001, "192.0.2.10", "198.51.100.20")
    add("IPv4 first fragment", ether(ip4(fragmented[:16], 17, ident=777, fragment=0x2000)))
    add("IPv4 second fragment", ether(ip4(fragmented[16:], 17, ident=777, fragment=2)))
    add("Unsupported experimental Ethernet protocol", ether(b"SYNTHETIC UNKNOWN", 0x88B5))
    whole = ether(ip4(udp(b"TRUNCATED DATA", 49000, 49001, "192.0.2.10", "198.51.100.20"), 17))
    add("Captured frame truncated inside IPv4 header", whole[:24], len(whole))
    files = {"synthetic_ethernet.pcap": classic(packets)}
    ng = section() + interface(1)
    for i, (packet, wire) in enumerate(packets):
        ng += enhanced(packet, (EPOCH + i) * 1_000_000 + 100000 + i * 1000, wire=wire)
    files["synthetic_ethernet.pcapng"] = ng
    raw = packets[0][0][14:]
    files["synthetic_raw_be_ns.pcap"] = classic([(raw, len(raw))], 101, ">", True)
    sll = struct.pack("!HHH8sH", 0, 1, 6, bytes.fromhex("0219000000010000"), 0x0800) + raw
    files["synthetic_sll.pcap"] = classic([(sll, len(sll))], 113)
    sll2 = struct.pack("!HHIHBB8s", 0x0800, 0, 1, 1, 0, 6, bytes.fromhex("0219000000010000")) + raw
    mixed = section() + interface(1) + enhanced(packets[0][0], EPOCH * 1_000_000 + 250000)
    mixed += section(">") + interface(101, 0x8A, 7, ">") + interface(276, 9, 0, ">")
    mixed += enhanced(raw, (EPOCH - 7) * 1024 + 512, 0, endian=">")
    mixed += enhanced(sll2, EPOCH * 10**9 + 750000000, 1, endian=">")
    files["synthetic_mixed_sections.pcapng"] = mixed
    loop = struct.pack("!6H", 0x2020, 0x8180, 1, 0, 0, 0) + b"\xc0\x0c\0\x01\0\x01"
    bad_dns = ether(ip4(udp(loop, 53, 53000, "192.0.2.53", "192.0.2.10"), 17, "192.0.2.53", "192.0.2.10"))
    files["synthetic_dns_pointer_loop.pcap"] = classic([(bad_dns, len(bad_dns))])
    files["synthetic_udp_truncated.pcap"] = classic([(whole[:14 + 20 + 8 + 4], len(whole))])
    files["invalid_unknown_interface.pcapng"] = section() + interface(1) + enhanced(packets[0][0], EPOCH * 1_000_000, 5)
    files["invalid_truncated_file.pcap"] = files["synthetic_ethernet.pcap"][:-5]
    files["invalid_not_capture.pcap"] = b"SYNTHETIC NOT A PACKET CAPTURE\n"
    manifest = {"synthetic": True, "network_calls": False, "note": "Documentation addresses and invented payloads. TLS bytes exercise record/ClientHello parsing, not an authenticated connection.",
        "ethernet_packet_descriptions": [{"frame": i + 1, "description": description} for i, description in enumerate(descriptions)],
        "mixed_section_expected_epoch_seconds": ["1700000000.250000000", "1700000000.500000000", "1700000000.750000000"],
        "files": []}
    for name, data in files.items():
        (ROOT / name).write_bytes(data)
        manifest["files"].append({"file": name, "bytes": len(data), "sha256": hashlib.sha256(data).hexdigest(),
                                 "expected_container_error": name.startswith("invalid_")})
    (ROOT / "fixture_manifest.json").write_text(json.dumps(manifest, indent=2) + "\n", encoding="utf-8")
    print(json.dumps({"synthetic_files": len(files), "main_packets": len(packets), "output": str(ROOT)}, indent=2))


if __name__ == "__main__":
    build()
