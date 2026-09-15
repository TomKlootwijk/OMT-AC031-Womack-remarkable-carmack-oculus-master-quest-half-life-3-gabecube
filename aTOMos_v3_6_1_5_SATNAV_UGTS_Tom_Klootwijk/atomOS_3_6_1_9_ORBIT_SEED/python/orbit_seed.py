"""ORBIT-SEED-R1: complete, lossless, canonical binary model seeds.

The compact bytes contain initial conditions and every numerical model parameter,
not a table of future target states. Code implementing the declared model remains
a shared runtime dependency; original observation/ephemeris files are provenance,
not replay dependencies. No pickle, object hooks or executable payloads are used.
"""
from __future__ import annotations

import hashlib
import json
import math
from pathlib import Path
import struct
import zlib

from self_reference import VARIABLES, WORD, compile_lut, parse_expression

PROFILE = "ORBIT-SEED-R1"
VERSION = "3.6.1.9"
MAGIC = b"ATOMORB1"
HEADER = struct.Struct("<8sHHII32s")
PLANE_HEADER = struct.Struct("<8sII")
PLANE_MAGIC = b"BITPLN64"
CODECS = {1: "canonical-zlib", 2: "bitplanes64-zlib"}
MAX_BYTES = 8 * 1024 * 1024
DOMAIN = b"atomOS:ORBIT-SEED-R1:canonical-binary\0"
REQUIRED = {"profile", "version", "object", "model", "stations", "query", "feedback", "provenance"}
OPTIONAL = {"description", "accuracy", "encoding"}


def _encode(value, depth=0, numbers=None, _budget=None):
    if _budget is None: _budget = [0]
    _budget[0] += 1
    if _budget[0] > 300000: raise ValueError("Seed structural limit exceeded")
    if depth > 48:
        raise ValueError("Seed nesting exceeds 48")
    if value is None:
        return b"n"
    if type(value) is bool:
        return b"t" if value else b"f"
    if type(value) is int:
        if -(1 << 63) <= value < (1 << 63):
            if numbers is not None:
                numbers.append(value & ((1 << 64) - 1)); return b"i"
            return b"i" + struct.pack("<q", value)
        if 0 <= value < (1 << 64):
            if numbers is not None:
                numbers.append(value); return b"u"
            return b"u" + struct.pack("<Q", value)
        raise ValueError("Integer exceeds 64-bit range")
    if type(value) is float:
        if not math.isfinite(value):
            raise ValueError("Nonfinite number in seed")
        if numbers is not None:
            numbers.append(struct.unpack("<Q", struct.pack("<d", value))[0]); return b"d"
        return b"d" + struct.pack("<d", value)
    if type(value) is str:
        data = value.encode("utf-8")
        return b"s" + struct.pack("<I", len(data)) + data
    if type(value) is list:
        if len(value) > 100000: raise ValueError("Excessive container size")
        return b"l" + struct.pack("<I", len(value)) + b"".join(_encode(v, depth + 1, numbers, _budget) for v in value)
    if type(value) is dict:
        if len(value) > 100000: raise ValueError("Excessive container size")
        if any(type(k) is not str for k in value):
            raise ValueError("Seed keys must be strings")
        return b"m" + struct.pack("<I", len(value)) + b"".join(
            _encode(k, depth + 1, numbers, _budget) + _encode(value[k], depth + 1, numbers, _budget) for k in sorted(value))
    raise ValueError("Unsupported seed value type: " + type(value).__name__)


class _Reader:
    def __init__(self, data, numbers=None):
        self.data, self.offset, self.items = data, 0, 0
        self.numbers, self.number_offset = numbers, 0

    def take(self, count):
        end = self.offset + count
        if end > len(self.data):
            raise ValueError("Truncated canonical payload")
        result = self.data[self.offset:end]
        self.offset = end
        return result

    def value(self, depth=0):
        self.items += 1
        if depth > 48 or self.items > 300000:
            raise ValueError("Seed structural limit exceeded")
        tag = self.take(1)
        if tag == b"n": return None
        if tag == b"t": return True
        if tag == b"f": return False
        if tag in (b"i", b"u", b"d"):
            if self.numbers is None:
                bits = self.take(8)
            else:
                if self.number_offset >= len(self.numbers): raise ValueError("Missing bit-plane number")
                bits = struct.pack("<Q", self.numbers[self.number_offset])
                self.number_offset += 1
            result = struct.unpack({b"i": "<q", b"u": "<Q", b"d": "<d"}[tag], bits)[0]
            if isinstance(result, float) and not math.isfinite(result):
                raise ValueError("Nonfinite canonical number")
            return result
        if tag not in (b"s", b"l", b"m"):
            raise ValueError("Unknown canonical tag")
        count = struct.unpack("<I", self.take(4))[0]
        if tag == b"s": return self.take(count).decode("utf-8")
        if count > 100000: raise ValueError("Excessive container size")
        if tag == b"l": return [self.value(depth + 1) for _ in range(count)]
        result, previous = {}, None
        for _ in range(count):
            key = self.value(depth + 1)
            if type(key) is not str or (previous is not None and key <= previous):
                raise ValueError("Map keys are not unique canonical strings")
            result[key], previous = self.value(depth + 1), key
        return result


def digest(value):
    return hashlib.sha256(DOMAIN + _encode(value)).hexdigest()


def words_to_bitplanes(numbers):
    """Plane b, group g stores bit b of up to 64 original words, lane j%64."""
    if any(type(n) is not int or not 0 <= n < (1 << 64) for n in numbers):
        raise ValueError("Bit-plane input must be unsigned 64-bit words")
    groups = (len(numbers) + 63) // 64
    planes = [0] * (64 * groups)
    for index, number in enumerate(numbers):
        group, lane = divmod(index, 64)
        for bit in range(64): planes[bit * groups + group] |= ((number >> bit) & 1) << lane
    return b"".join(struct.pack("<Q", word) for word in planes)


def bitplanes_to_words(data, count):
    if type(count) is not int or not 0 <= count <= 300000: raise ValueError("Invalid bit-plane word count")
    groups = (count + 63) // 64
    if len(data) != 64 * groups * 8: raise ValueError("Bit-plane length mismatch")
    planes = [row[0] for row in struct.iter_unpack("<Q", data)]
    if count % 64:
        padding = ((1 << 64) - 1) ^ ((1 << (count % 64)) - 1)
        if any(planes[bit * groups + groups - 1] & padding for bit in range(64)):
            raise ValueError("Nonzero bit-plane padding")
    numbers = [0] * count
    for index in range(count):
        group, lane = divmod(index, 64)
        for bit in range(64): numbers[index] |= ((planes[bit * groups + group] >> lane) & 1) << bit
    return numbers


def _encode_planes(seed):
    numbers = []
    template = _encode(seed, numbers=numbers)
    return PLANE_HEADER.pack(PLANE_MAGIC, len(template), len(numbers)) + template + words_to_bitplanes(numbers)


def _decode_planes(payload, canonical_size):
    if len(payload) < PLANE_HEADER.size: raise ValueError("Truncated bit-plane header")
    magic, template_size, count = PLANE_HEADER.unpack_from(payload)
    if magic != PLANE_MAGIC or count > 300000: raise ValueError("Unsupported bit-plane payload")
    if template_size + 8 * count != canonical_size: raise ValueError("Bit-plane canonical length mismatch")
    split = PLANE_HEADER.size + template_size
    if split > len(payload): raise ValueError("Truncated bit-plane template")
    reader = _Reader(payload[PLANE_HEADER.size:split], bitplanes_to_words(payload[split:], count))
    seed = reader.value()
    if reader.offset != template_size or reader.number_offset != count:
        raise ValueError("Unconsumed bit-plane structure or words")
    raw = _encode(seed)
    if len(raw) != canonical_size or _encode_planes(seed) != payload:
        raise ValueError("Noncanonical bit-plane encoding")
    return raw


def _finite(value, name):
    if type(value) not in (float, int) or not math.isfinite(value):
        raise ValueError(name + " must be finite")
    return float(value)


def validate_feedback(feedback):
    required = {"q0", "present", "sets", "equations", "predicates", "cadence"}
    if type(feedback) is not dict or set(feedback) != required:
        raise ValueError("Feedback fields must be " + str(sorted(required)))
    for name in ("q0", "present"):
        if type(feedback[name]) is not int or not 0 <= feedback[name] <= WORD:
            raise ValueError(name + " must be uint32")
    if feedback["q0"] & ~feedback["present"]:
        raise ValueError("q0 exceeds present bits")
    sets = feedback["sets"]
    if type(sets) is not list or len(sets) != 2:
        raise ValueError("Exactly two explicit ASA/NA mask sets required")
    for masks in sets:
        if type(masks) is not dict or set(masks) != {"asa_mask", "na_mask", "boundary_mask"}:
            raise ValueError("Each set requires ASA, NA and boundary masks")
        if any(type(v) is not int or not 0 <= v <= WORD for v in masks.values()):
            raise ValueError("Masks must be uint32")
    if type(feedback["equations"]) is not dict or set(feedback["equations"]) != set(VARIABLES):
        raise ValueError("Explicit x/j/k equations required")
    for key, variables in VARIABLES.items():
        parse_expression(feedback["equations"][key], variables)
    p = feedback["predicates"]
    if set(p) != {"near_mask_deg", "age_warning_s", "rising_rate_deg_s"}:
        raise ValueError("Unknown/missing geometry predicate thresholds")
    if any(_finite(v, k) < 0 for k, v in p.items()):
        raise ValueError("Predicate thresholds must be nonnegative")
    c = feedback["cadence"]
    if set(c) != {"fine_bits", "fine_s", "coarse_s"}:
        raise ValueError("Unknown/missing cadence fields")
    if type(c["fine_bits"]) is not int or not 0 <= c["fine_bits"] <= WORD:
        raise ValueError("fine_bits must be uint32")
    if not 0 < _finite(c["fine_s"], "fine_s") <= _finite(c["coarse_s"], "coarse_s") <= 86400:
        raise ValueError("Require 0 < fine <= coarse <= 86400 seconds")


def validate(seed):
    if type(seed) is not dict or not REQUIRED <= set(seed) or set(seed) - REQUIRED - OPTIONAL:
        raise ValueError("Unknown/missing root seed fields")
    if seed["profile"] != PROFILE or seed["version"] != VERSION:
        raise ValueError("Unsupported seed profile/version")
    if type(seed["object"]) is not dict or not {"id", "orbit_class"} <= set(seed["object"]):
        raise ValueError("Object ID and orbit class required")
    if type(seed["model"]) is not dict or not seed["model"]:
        raise ValueError("A complete physical model is required")
    from orbit_dynamics import validate_model
    validate_model(seed["model"])
    _encode(seed)
    stations = seed["stations"]
    if type(stations) is not list or not stations:
        raise ValueError("At least one explicit station required")
    seen = set()
    for station in stations:
        if type(station) is not dict or set(station) != {"id", "lat_deg", "lon_deg", "height_m", "elevation_mask_deg", "description"}:
            raise ValueError("Station requires ID, WGS84 coordinates and elevation mask")
        if type(station["id"]) is not str or not station["id"] or station["id"] in seen:
            raise ValueError("Station IDs must be nonempty and unique")
        seen.add(station["id"])
        if not -90 <= _finite(station["lat_deg"], "latitude") <= 90:
            raise ValueError("Latitude out of range")
        if not -180 <= _finite(station["lon_deg"], "longitude") <= 180:
            raise ValueError("Longitude out of range")
        if not -500 <= _finite(station["height_m"], "height") <= 10000:
            raise ValueError("Declared ground station height out of range")
        if not -5 <= _finite(station["elevation_mask_deg"], "mask") < 90:
            raise ValueError("Elevation mask out of range")
    query = seed["query"]
    if set(query) != {"start_s", "end_s", "tick_s", "chart_r0_m", "phi_rad", "event_step_s", "event_tolerance_s"}:
        raise ValueError("Unknown/missing query fields")
    if _finite(query["end_s"], "end") < _finite(query["start_s"], "start"):
        raise ValueError("Query interval is reversed")
    if not seed["model"]["domain_s"][0] <= query["start_s"] <= query["end_s"] <= seed["model"]["domain_s"][1]:
        raise ValueError("Query interval exceeds physical model domain")
    for key in ("tick_s", "chart_r0_m", "event_step_s", "event_tolerance_s"):
        if _finite(query[key], key) <= 0: raise ValueError(key + " must be positive")
    _finite(query["phi_rad"], "phi")
    validate_feedback(seed["feedback"])
    if type(seed["provenance"]) is not dict or not seed["provenance"]:
        raise ValueError("Source provenance required")
    return seed


def pack_bytes(seed, codec="bitplanes64-zlib"):
    validate(seed)
    raw = _encode(seed)
    if len(raw) > MAX_BYTES: raise ValueError("Seed exceeds format limit")
    codec_id = next((number for number, name in CODECS.items() if name == codec), None)
    if codec_id is None: raise ValueError("Unsupported seed codec")
    payload = raw if codec_id == 1 else _encode_planes(seed)
    compressed = zlib.compress(payload, level=9)
    if len(compressed) > MAX_BYTES: raise ValueError("Packed seed exceeds format limit")
    return HEADER.pack(MAGIC, 1, codec_id, len(compressed), len(raw), hashlib.sha256(DOMAIN + raw).digest()) + compressed


def unpack_bytes(data):
    if len(data) < HEADER.size: raise ValueError("Truncated seed header")
    magic, version, codec, packed_size, raw_size, expected = HEADER.unpack_from(data)
    if (magic, version) != (MAGIC, 1) or codec not in CODECS: raise ValueError("Unsupported seed header")
    if not 0 < raw_size <= MAX_BYTES or not 0 < packed_size <= MAX_BYTES:
        raise ValueError("Seed length exceeds limits")
    if len(data) != HEADER.size + packed_size: raise ValueError("Seed length/trailing bytes mismatch")
    dec = zlib.decompressobj()
    try:
        limit = raw_size if codec == 1 else raw_size + PLANE_HEADER.size + 504
        payload = dec.decompress(data[HEADER.size:], limit + 1)
    except zlib.error as exc:
        raise ValueError("Invalid seed compression") from exc
    if len(payload) > limit or not dec.eof or dec.unused_data or dec.unconsumed_tail:
        raise ValueError("Invalid compressed payload length/end")
    raw = payload if codec == 1 else _decode_planes(payload, raw_size)
    if len(raw) != raw_size: raise ValueError("Invalid canonical payload length")
    if hashlib.sha256(DOMAIN + raw).digest() != expected: raise ValueError("Seed digest mismatch")
    reader = _Reader(raw)
    seed = reader.value()
    if reader.offset != len(raw) or _encode(seed) != raw:
        raise ValueError("Noncanonical or trailing payload")
    return validate(seed)


def load(path):
    path = Path(path)
    if path.stat().st_size > MAX_BYTES + HEADER.size: raise ValueError("Seed file too large")
    return unpack_bytes(path.read_bytes())


def load_json(path):
    def unique(pairs):
        result = {}
        for key, value in pairs:
            if key in result: raise ValueError("Duplicate JSON key: " + key)
            result[key] = value
        return result
    return validate(json.loads(Path(path).read_text(encoding="utf-8-sig"), object_pairs_hook=unique,
                               parse_constant=lambda s: (_ for _ in ()).throw(ValueError(s))))


def inspect_bytes(data):
    seed = unpack_bytes(data)
    _, _, codec, packed_size, raw_size, content_hash = HEADER.unpack_from(data)
    return {"profile": PROFILE, "object": seed["object"], "file_bytes": len(data),
            "file_sha256": hashlib.sha256(data).hexdigest(), "seed_sha256": content_hash.hex(),
            "model_sha256": digest(seed["model"]), "payload_uncompressed_bytes": raw_size,
            "payload_compressed_bytes": packed_size, "header_bytes": HEADER.size, "codec": CODECS[codec],
            "dependencies": "Declared model runtime; no original observations or future target trajectory needed",
            "numeric_encoding": "Lossless 64 bit planes in uint64 words; original binary64/int64/uint64 bits restored" if codec == 2 else "Lossless IEEE754 binary64; no orbital coordinate quantization",
            "arithmetic_scope": "Packing is exact; native orbit propagation still uses binary64 floating point",
            "stations": [s["id"] for s in seed["stations"]], "query": seed["query"]}


def feedback_luts(feedback):
    validate_feedback(feedback)
    return {key + "_lut": compile_lut(parse_expression(feedback["equations"][key], variables))
            for key, variables in VARIABLES.items()}


def transition_ast(feedback, q, drive):
    """Independent expression replay; both stages preserve whole-word absorption."""
    validate_feedback(feedback)
    if type(q) is not int or type(drive) is not int or not 0 <= q <= WORD or not 0 <= drive <= WORD:
        raise ValueError("State and drive must be uint32")
    present = feedback["present"]
    expressions = {k: parse_expression(feedback["equations"][k], variables) for k, variables in VARIABLES.items()}
    x = expressions["x"].evaluate({"q": q, "d": drive})
    value, stages = x, []
    for masks in feedback["sets"]:
        asa = value & masks["asa_mask"] & present
        na = asa & masks["na_mask"]
        hits = (na & masks["boundary_mask"]).bit_count()
        output = 0 if hits else na
        stages.append({"input": value, "asa": asa, "na": na, "hits": hits, "output": output})
        value = output
    values = {"q": q, "y": value, "d": drive}
    j, k = expressions["j"].evaluate(values), expressions["k"].evaluate(values)
    after = ((j & ~q) | (~k & q)) & present
    return {"before": q, "drive": drive, "x": x, "stages": stages,
            "output": value, "j": j, "k": k, "after": after}


def default_feedback():
    return {"q0": 0, "present": 31,
            "sets": [{"asa_mask": 31, "na_mask": 31, "boundary_mask": 0},
                     {"asa_mask": 31, "na_mask": 31, "boundary_mask": 0}],
            "equations": {"x": "q | d", "j": "y & d", "k": "~d"},
            "predicates": {"near_mask_deg": 3., "age_warning_s": 86400., "rising_rate_deg_s": 0.},
            "cadence": {"fine_bits": 6, "fine_s": 30., "coarse_s": 300.}}


def default_stations():
    return [
        {"id": "delft_demo", "lat_deg": 51.986, "lon_deg": 4.387, "height_m": 0.,
         "elevation_mask_deg": 10., "description": "Demonstration station; not a surveyed receiver location"},
        {"id": "singapore_demo", "lat_deg": 1.35, "lon_deg": 103.82, "height_m": 0.,
         "elevation_mask_deg": 10., "description": "Demonstration station for Asian GEO visibility"}]


def default_query(start=0., end=604800.):
    return {"start_s": float(start), "end_s": float(end), "tick_s": 1., "chart_r0_m": 1.e9,
            "phi_rad": 0., "event_step_s": 120., "event_tolerance_s": .01}
