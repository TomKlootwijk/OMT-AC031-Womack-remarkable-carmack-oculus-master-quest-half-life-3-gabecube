"""Capture an explicitly public NTRIP stream, preserving timing and source evidence.

This helper is for reproducible validation captures. The incremental production
receiver is tools/live_satnav.py. No registration or credentials are fabricated.
"""
from __future__ import annotations
import argparse
from collections import Counter
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import socket
import time


def utc():
    return datetime.now(timezone.utc).isoformat()


def crc24q(data):
    crc = 0
    for byte in data:
        crc ^= byte << 16
        for _ in range(8):
            crc <<= 1
            if crc & 0x1000000:
                crc ^= 0x1864CFB
    return crc & 0xFFFFFF


def inspect_frames(data):
    counts, gps_tows = Counter(), []
    i = bad = 0
    while i + 6 <= len(data):
        if data[i] != 0xD3 or data[i + 1] & 0xFC:
            i += 1
            continue
        size = ((data[i + 1] & 3) << 8) + data[i + 2] + 6
        if i + size > len(data):
            break
        frame = data[i:i + size]
        if crc24q(frame[:-3]) != int.from_bytes(frame[-3:], 'big'):
            bad += 1
            i += 1
            continue
        payload = frame[3:-3]
        msg = (payload[0] << 4) | (payload[1] >> 4)
        counts[msg] += 1
        if msg in (1001, 1002, 1003, 1004, 1074, 1075, 1076, 1077):
            bits = int.from_bytes(payload, 'big')
            tow = (bits >> (len(payload) * 8 - 54)) & ((1 << 30) - 1)
            gps_tows.append(tow / 1000)
        i += size
    return {'valid_frames': sum(counts.values()), 'message_counts': dict(sorted(counts.items())),
            'crc_errors': bad, 'gps_tow_first': gps_tows[0] if gps_tows else None,
            'gps_tow_last': gps_tows[-1] if gps_tows else None,
            'distinct_gps_epochs': len(set(gps_tows)), 'trailing_bytes': len(data) - i}


def main():
    p = argparse.ArgumentParser(description=__doc__)
    p.add_argument('--host', default='crtk.net')
    p.add_argument('--port', type=int, default=2101)
    p.add_argument('--mountpoint', default='LIENSS')
    p.add_argument('--seconds', type=float, default=300)
    p.add_argument('--out', type=Path, required=True)
    args = p.parse_args()
    if not (0 < args.seconds <= 3600):
        p.error('--seconds must be between zero and 3600')
    args.out.mkdir(parents=True, exist_ok=False)
    manifest = {'kind': 'live_public_internet_receiver_capture', 'started_utc': utc(),
                'endpoint': f'ntrip://{args.host}:{args.port}/{args.mountpoint}',
                'authentication': 'none', 'requested_seconds': args.seconds,
                'status': 'connecting', 'source_attribution': 'Centipede-RTK' if 'centipede' in args.host or args.host == 'crtk.net' else args.host}
    (args.out / 'capture.json').write_text(json.dumps(manifest, indent=2))
    request = (f'GET /{args.mountpoint} HTTP/1.0\r\n'
               f'Host: {args.host}:{args.port}\r\n'
               'User-Agent: NTRIP atomOS-GNSS-validation/3.6.1.8\r\n'
               'Accept: */*\r\nConnection: close\r\n\r\n').encode('ascii')
    started = time.monotonic()
    wire_bytes = bytearray()
    chunks = []
    error = None
    try:
        with socket.create_connection((args.host, args.port), timeout=10) as sock:
            sock.settimeout(5)
            sock.sendall(request)
            with (args.out / 'wire.bin').open('wb') as stream:
                while time.monotonic() - started < args.seconds:
                    try:
                        chunk = sock.recv(65536)
                    except socket.timeout:
                        continue
                    if not chunk:
                        break
                    chunks.append({'received_utc': utc(), 'elapsed_seconds': time.monotonic() - started,
                                   'wire_offset': len(wire_bytes), 'bytes': len(chunk)})
                    wire_bytes.extend(chunk)
                    stream.write(chunk)
                    stream.flush()
    except Exception as exc:
        error = f'{type(exc).__name__}: {exc}'
    sep = wire_bytes.find(b'\r\n\r\n')
    # NTRIP v1 permits ICY followed immediately by RTCM after one CRLF.
    if wire_bytes.startswith(b'ICY 200 OK\r\n\xd3'):
        sep, width = len(b'ICY 200 OK'), 2
    else:
        width = 4
    if sep < 0:
        header, payload = bytes(wire_bytes), b''
    else:
        header, payload = bytes(wire_bytes[:sep]), bytes(wire_bytes[sep + width:])
    accepted = header.startswith((b'ICY 200 OK', b'HTTP/1.0 200', b'HTTP/1.1 200'))
    if not accepted:
        payload = b''
    (args.out / 'capture.rtcm3').write_bytes(payload)
    (args.out / 'chunks.json').write_text(json.dumps(chunks, indent=2))
    manifest.update({'finished_utc': utc(), 'elapsed_seconds': time.monotonic() - started,
                     'wire_bytes': len(wire_bytes), 'payload_bytes': len(payload),
                     'response_header': header.decode('ascii', errors='replace'), 'error': error,
                     'status': 'captured' if accepted and payload else 'failed',
                     'wire_sha256': hashlib.sha256(wire_bytes).hexdigest(),
                     'rtcm_sha256': hashlib.sha256(payload).hexdigest(),
                     'frame_inspection': inspect_frames(payload)})
    (args.out / 'capture.json').write_text(json.dumps(manifest, indent=2))
    print(json.dumps(manifest, indent=2))
    return 0 if accepted and payload else 1


if __name__ == '__main__':
    raise SystemExit(main())
