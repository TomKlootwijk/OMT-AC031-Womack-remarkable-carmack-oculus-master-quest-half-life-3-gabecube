"""Independent scalar ASA oracle. Pure Python, no compiled-core calls."""
from __future__ import annotations
import json
import math
import struct
from pathlib import Path
TAU = 2 * math.pi
INVALID = 0xFFFFFFFF

def f32(x: float) -> float:
    return struct.unpack('<f', struct.pack('<f', x))[0]

def wrap(x: float) -> float:
    r = math.fmod(x, TAU)
    if r < 0:
        r += TAU
    return 0.0 if r >= TAU else r

def signed_angle(x: float) -> float:
    r = wrap(x)
    return r - TAU if r >= math.pi else r

def address(r: int, p: int, width: int, layout: int) -> int:
    if layout == 0:
        return r * width + p
    local = sum(((r >> b) & 1) << (2*b) for b in range(3))
    local |= sum(((p >> b) & 1) << (2*b+1) for b in range(3))
    return ((r // 8) * (width // 8) + p // 8) * 64 + local

def lens(delta: float, config: dict, warp: list[tuple[float, float]]) -> tuple[float, float]:
    q = wrap(delta) / TAU * config['warp_bins']
    i = min(int(q), config['warp_bins'] - 1)
    f = q - i
    a, b = warp[i], warp[(i+1) % config['warp_bins']]
    return a[0] + f*(b[0]-a[0]), a[1] + f*(b[1]-a[1])

def side(rho: float, delta: float, c: dict, image: list[float], mask: list[int], warp: list[tuple[float,float]]) -> tuple[float, int, int]:
    if not c['pupil_min'] <= rho < c['pupil_max'] or abs(delta) > c['alpha']:
        return 0.0, 0, INVALID
    dr, dp = lens(delta, c, warp)
    r, phi = rho + dr, wrap(c['axis'] + delta + dp)
    if not math.isfinite(r) or not c['rho_min'] <= r < c['rho_max']:
        return 0.0, 0, INVALID
    ir = min(int((r-c['rho_min'])/(c['rho_max']-c['rho_min'])*c['rho_bins']), c['rho_bins']-1)
    ip = min(int(phi/TAU*c['phi_bins']), c['phi_bins']-1)
    key = ir*c['phi_bins']+ip
    a = address(ir, ip, c['phi_bins'], c['layout'])
    if (mask[a//32] >> (a % 32)) & 1:
        return 0.0, 0, key
    return image[a], 1, key

def evaluate(sample: tuple[float,float], c: dict, image: list[float], mask: list[int], warp: list[tuple[float,float]]) -> tuple:
    rho, phi = sample
    if not all(map(math.isfinite, sample)):
        return 0.0, 0.0, 0.0, 0.0, 8, INVALID, INVALID, 0
    d = signed_angle(wrap(phi)-c['axis']+c['hinge'])
    l, lv, li = side(rho, d, c, image, mask, warp)
    r, rv, ri = side(rho, -d, c, image, mask, warp)
    both = lv and rv
    return l, r, f32((l+r)*.5) if both else 0.0, 0.0, lv | (rv << 1) | (4 if both else 0), li, ri, 0

def read_records(path: Path, fmt: str) -> list[tuple]:
    raw = path.read_bytes()
    if len(raw) % struct.calcsize(fmt):
        raise ValueError(f'truncated record file: {path}')
    return list(struct.iter_unpack(fmt, raw))

def verify_directory(path: Path) -> dict:
    meta = json.loads((path/'run.json').read_text())
    c = meta['config']
    image = [x[0] for x in read_records(path/'image.f32', '<f')]
    mask = [x[0] for x in read_records(path/'mask.u32', '<I')]
    warp = read_records(path/'warp.f32x2', '<2f')
    samples = read_records(path/'samples.f64x2', '<2d')
    actual = read_records(path/'results.bin', '<4f4I')
    cells = c['rho_bins']*c['phi_bins']
    if len(image) != cells or len(mask) != (cells+31)//32 or len(warp) != c['warp_bins'] or len(samples) != meta['samples'] or len(actual) != len(samples):
        raise ValueError('file length does not agree with run metadata')
    maximum = 0.0
    for i, (z, a) in enumerate(zip(samples, actual)):
        b = evaluate(z, c, image, mask, warp)
        if a[4:] != b[4:]:
            raise AssertionError(f'flags/coordinate mismatch at sample {i}: {a[4:]} != {b[4:]}')
        error = max(abs(x-y) for x,y in zip(a[:4], b[:4]))
        if not all(math.isfinite(x) for x in a[:4]) or error > 2e-6:
            raise AssertionError(f'numerical mismatch at sample {i}: {error}')
        maximum = max(maximum, error)
    return {'status':'pass', 'oracle':'independent_python', 'samples_checked':len(samples), 'maximum_absolute_error':maximum}
