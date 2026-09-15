"""Exact reference subset for ATOMOS-HINGE-R1, not an XOPSEED1 executor.

Python int/Fraction are authoritative. No operation silently converts to float.
The upload envelope includes definitions, operands, dependencies and state.
"""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import copy
import hashlib
import json
import math
import struct
from typing import Any


PROFILE = "ATOMOS-HINGE-R1"
MAGIC = b"AHNGBPL1"
MAX_ENVELOPE_BYTES = 64 * 1024 * 1024
DIMLESS = (0, 0, 0, 0, 0, 0, 0)
LENGTH = (1, 0, 0, 0, 0, 0, 0)
TIME = (0, 0, 1, 0, 0, 0, 0)
VELOCITY = (1, 0, -1, 0, 0, 0, 0)


class DomainError(ValueError):
    pass


class MissingInput(ValueError):
    pass


class UnsupportedOperation(ValueError):
    pass


def _fraction(value: Any) -> Fraction:
    if isinstance(value, Fraction):
        return value
    if type(value) is int:
        return Fraction(value)
    raise TypeError("exact coefficient must be int or Fraction; floats are not admitted")


@dataclass(frozen=True)
class Phi:
    """a+b*phi in Q(phi), phi positive root of x*x-x-1.

    Equality, sign and floor are exact, including arbitrarily large coefficients.
    """
    a: Fraction = Fraction(0)
    b: Fraction = Fraction(0)

    def __post_init__(self):
        object.__setattr__(self, "a", _fraction(self.a))
        object.__setattr__(self, "b", _fraction(self.b))

    @staticmethod
    def of(value: Any) -> "Phi":
        return value if isinstance(value, Phi) else Phi(_fraction(value))

    def __add__(self, other):
        other = Phi.of(other)
        return Phi(self.a + other.a, self.b + other.b)

    __radd__ = __add__

    def __neg__(self):
        return Phi(-self.a, -self.b)

    def __sub__(self, other):
        return self + (-Phi.of(other))

    def __rsub__(self, other):
        return Phi.of(other) - self

    def __mul__(self, other):
        other = Phi.of(other)
        return Phi(self.a * other.a + self.b * other.b,
                   self.a * other.b + self.b * other.a + self.b * other.b)

    __rmul__ = __mul__

    def inverse(self):
        norm = self.a * self.a + self.a * self.b - self.b * self.b
        if norm == 0:
            raise DomainError("inverse of zero")
        return Phi((self.a + self.b) / norm, -self.b / norm)

    def __truediv__(self, other):
        return self * Phi.of(other).inverse()

    def __rtruediv__(self, other):
        return Phi.of(other) / self

    def __pow__(self, exponent):
        if type(exponent) is not int:
            raise TypeError("integer exponent required")
        if exponent < 0:
            return self.inverse() ** (-exponent)
        value, base = Phi(1), self
        while exponent:
            if exponent & 1:
                value = value * base
            base = base * base
            exponent >>= 1
        return value

    def sign(self) -> int:
        # 2*x = A+B*sqrt(5). Rational comparisons decide the sign exactly.
        A, B = 2 * self.a + self.b, self.b
        sa, sb = (A > 0) - (A < 0), (B > 0) - (B < 0)
        if not sb:
            return sa
        if not sa or sa == sb:
            return sb
        delta = A * A - 5 * B * B
        return sa if delta > 0 else sb if delta < 0 else 0

    def floor(self) -> int:
        D = math.lcm(self.a.denominator, self.b.denominator)
        A = 2 * self.a.numerator * (D // self.a.denominator)
        B = self.b.numerator * (D // self.b.denominator)
        A += B
        root = math.isqrt(5 * B * B)
        # For nonzero rational B, sqrt(5*B**2) is irrational. Its fractional
        # part cannot cross an integer division boundary of the denominator.
        numerator = A + root if B >= 0 else A - root - 1
        return numerator // (2 * D)

    def __lt__(self, other):
        return (self - other).sign() < 0

    def __le__(self, other):
        return (self - other).sign() <= 0

    def __gt__(self, other):
        return (self - other).sign() > 0

    def __ge__(self, other):
        return (self - other).sign() >= 0

    def __bool__(self):
        return self.sign() != 0


PHI = Phi(0, 1)


def phi_turn(index: int) -> Phi:
    """Exact fractional turns of index/phi; no trig evaluation is implied."""
    if type(index) is not int:
        raise TypeError("integer branch index required")
    turn = index * (PHI - 1)
    return turn - turn.floor()


def phi_branch(index: int, radius=1) -> dict:
    """Retain the actual polar operator expression, rather than sample trig."""
    return {"profile": "PHI-POLAR-EXPRESSION-R1", "index": index,
            "radius": Phi.of(radius), "turn": phi_turn(index),
            "position_expression": ["polar", "radius", ["mul", ["mul", 2, "PI"], "turn"]],
            "numeric_cartesian_status": "UNKNOWN"}


def _wrap_turn(value) -> Phi:
    value = Phi.of(value)
    return value - value.floor()


def chart_normalize(rho, theta_turn, phi_phase_turn=0, *, lo=0, period=1,
                    orientation=0, profile="reflective_klein") -> dict:
    rho, lo, period = Phi.of(rho), Phi.of(lo), Phi.of(period)
    if period.sign() <= 0 or type(orientation) is not int or orientation not in (0, 1):
        raise DomainError("positive chart period and one orientation bit required")
    if profile not in ("reflective_klein", "source_half_turn"):
        raise DomainError("unknown chart profile")
    original_theta, original_phase = Phi.of(theta_turn), Phi.of(phi_phase_turn)
    theta_winding, phase_winding = original_theta.floor(), original_phase.floor()
    theta, phase = original_theta - theta_winding, original_phase - phase_winding
    winding = ((rho - lo) / period).floor()
    if winding & 1:
        theta = _wrap_turn(Phi(Fraction(1, 2)) - theta if profile == "reflective_klein"
                           else theta + Fraction(1, 2))
        phase = _wrap_turn(-phase)
        orientation ^= 1
    return {"rho": rho - winding * period, "theta_turn": theta,
            "phi_phase_turn": phase, "orientation": orientation,
            "winding": winding, "theta_winding": theta_winding,
            "phi_phase_winding": phase_winding, "period": period, "lo": lo, "profile": profile}


def chart_lift(record: dict) -> dict:
    """Inverse lift including each original independent angular winding."""
    theta, phase = Phi.of(record["theta_turn"]), Phi.of(record["phi_phase_turn"])
    orientation, winding = record["orientation"], record["winding"]
    profile = record["profile"]
    theta_winding, phase_winding = record["theta_winding"], record["phi_phase_winding"]
    rho, lo, period = Phi.of(record["rho"]), Phi.of(record["lo"]), Phi.of(record["period"])
    if (profile not in ("reflective_klein", "source_half_turn")
            or any(type(n) is not int for n in (winding, theta_winding, phase_winding))
            or type(orientation) is not int or orientation not in (0, 1)
            or period.sign() <= 0 or not lo <= rho < lo + period
            or not Phi(0) <= theta < Phi(1) or not Phi(0) <= phase < Phi(1)):
        raise DomainError("invalid chart lift")
    if winding & 1:
        theta = _wrap_turn(Fraction(1, 2) - theta if profile == "reflective_klein"
                           else theta - Fraction(1, 2))
        phase, orientation = _wrap_turn(-phase), orientation ^ 1
    return {"rho": rho + winding * period, "theta_turn": theta + theta_winding,
            "phi_phase_turn": phase + phase_winding, "orientation": orientation}


def _hex_int(value: int) -> str:
    return ("-" if value < 0 else "") + format(abs(value), "x")


def _read_hex(value) -> int:
    if not isinstance(value, str) or not value:
        raise ValueError("canonical hex integer required")
    digits = value[1:] if value.startswith("-") else value
    if (not digits or any(c not in "0123456789abcdef" for c in digits)
            or (len(digits) > 1 and digits[0] == "0") or value == "-0"):
        raise ValueError("noncanonical hex integer")
    return int(value, 16)


def _encode(value):
    if value is None or type(value) in (bool, str):
        return value
    if type(value) is int:
        return {"$int": _hex_int(value)}
    if isinstance(value, Fraction):
        return {"$rat": [_hex_int(value.numerator), _hex_int(value.denominator)]}
    if isinstance(value, Phi):
        return {"$phi": [_encode(value.a), _encode(value.b)]}
    if isinstance(value, (list, tuple)):
        return [_encode(v) for v in value]
    if isinstance(value, dict):
        if any(not isinstance(k, str) or k.startswith("$") for k in value):
            raise ValueError("record keys must be strings outside the reserved $ namespace")
        return {k: _encode(v) for k, v in value.items()}
    raise TypeError("unsupported exact serialization value")


def _decode(value):
    if isinstance(value, list):
        return [_decode(v) for v in value]
    if isinstance(value, dict):
        if set(value) == {"$int"}:
            return _read_hex(value["$int"])
        if set(value) == {"$rat"}:
            pair = value["$rat"]
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("invalid rational")
            n, d = map(_read_hex, pair)
            if d <= 0 or math.gcd(n, d) != 1:
                raise ValueError("noncanonical rational")
            return Fraction(n, d)
        if set(value) == {"$phi"}:
            pair = value["$phi"]
            if not isinstance(pair, list) or len(pair) != 2:
                raise ValueError("invalid phi pair")
            a, b = map(_decode, pair)
            if not isinstance(a, Fraction) or not isinstance(b, Fraction):
                raise ValueError("phi coefficients must be canonical rationals")
            return Phi(a, b)
        if any(k.startswith("$") for k in value):
            raise ValueError("unknown reserved type")
        return {k: _decode(v) for k, v in value.items()}
    if value is None or type(value) in (str, bool):
        return value
    raise ValueError("untagged number is not canonical")


def canonical_bytes(document: dict) -> bytes:
    return json.dumps(_encode(document), sort_keys=True, separators=(",", ":"),
                      ensure_ascii=True, allow_nan=False).encode("ascii")


def _no_duplicates(pairs):
    result = {}
    for key, value in pairs:
        if key in result:
            raise ValueError("duplicate record key")
        result[key] = value
    return result


def _transpose(block: bytes) -> bytes:
    words = struct.unpack("<64Q", block)
    planes = [sum(((word >> bit) & 1) << lane for lane, word in enumerate(words))
              for bit in range(64)]
    return struct.pack("<64Q", *planes)


def pack_document(document: dict) -> bytes:
    raw = canonical_bytes(document)
    if len(raw) > MAX_ENVELOPE_BYTES:
        raise ValueError("declared envelope resource limit")
    padded = raw + bytes((-len(raw)) % 512)
    payload = b"".join(_transpose(padded[i:i + 512]) for i in range(0, len(padded), 512))
    return MAGIC + struct.pack("<Q", len(raw)) + hashlib.sha256(raw).digest() + payload


def unpack_document(blob: bytes, *, max_bytes=MAX_ENVELOPE_BYTES) -> dict:
    if not isinstance(blob, bytes) or len(blob) < 48 or blob[:8] != MAGIC:
        raise ValueError("wrong or truncated hinge envelope")
    length = struct.unpack("<Q", blob[8:16])[0]
    if not 0 < length <= min(max_bytes, MAX_ENVELOPE_BYTES):
        raise ValueError("declared length outside resource limit")
    if len(blob) != 48 + 512 * ((length + 511) // 512):
        raise ValueError("truncated or trailing envelope data")
    padded = b"".join(_transpose(blob[i:i + 512]) for i in range(48, len(blob), 512))
    if any(padded[length:]):
        raise ValueError("nonzero bit-plane padding")
    raw = padded[:length]
    if hashlib.sha256(raw).digest() != blob[16:48]:
        raise ValueError("envelope digest mismatch")
    parsed = json.loads(raw.decode("ascii"), object_pairs_hook=_no_duplicates)
    document = _decode(parsed)
    if not isinstance(document, dict) or canonical_bytes(document) != raw:
        raise ValueError("noncanonical seed record")
    return document


def _dimension(dimension):
    if (not isinstance(dimension, (list, tuple)) or len(dimension) != 7
            or any(type(d) is not int for d in dimension)):
        raise DomainError("seven integer SI exponents required")
    return tuple(dimension)


@dataclass(frozen=True)
class Value:
    data: Any
    dimension: tuple
    frame: str | None = None
    primitive: str = "scalar"
    is_sdf: bool = False


def _scalar(data, dimension=DIMLESS):
    return Value(Phi.of(data), _dimension(dimension))


def _vector(data, dimension, frame):
    if not isinstance(data, (list, tuple)) or len(data) != 3 or not isinstance(frame, str) or not frame:
        raise DomainError("three components and explicit frame required")
    return Value(tuple(Phi.of(v) for v in data), _dimension(dimension), frame, "vec3")


def _same_geometry(a, b):
    if a.dimension != b.dimension or a.frame != b.frame or a.primitive != "vec3" or b.primitive != "vec3":
        raise DomainError("vector frame/dimension mismatch")


def _dot(a, b):
    return sum((x * y for x, y in zip(a, b)), Phi())


def plane_guard(point, normal, offset=0) -> Phi:
    point, normal = tuple(map(Phi.of, point)), tuple(map(Phi.of, normal))
    if len(point) != 3 or len(normal) != 3 or _dot(normal, normal).sign() <= 0:
        raise DomainError("nonzero three-dimensional plane normal required")
    return _dot(point, normal) - Phi.of(offset)


def sphere_guard(point, center=(0, 0, 0), radius=1) -> Phi:
    radius = Phi.of(radius)
    if radius.sign() <= 0 or len(point) != 3 or len(center) != 3:
        raise DomainError("positive radius and three-dimensional points required")
    d = tuple(Phi.of(x) - Phi.of(c) for x, c in zip(point, center))
    return _dot(d, d) - radius * radius


def psi_excludes_ball(kind, node_center, descendant_radius, *, normal=(1, 0, 0),
                      offset=0, center=(0, 0, 0), radius=1) -> bool:
    """Exact sufficient exclusion, conditional on a full descendant-ball bound.

    Equality is retained. This does not establish that the supplied radius
    covers the actual descendants or their entire time interval.
    """
    R = Phi.of(descendant_radius)
    if R.sign() < 0:
        raise DomainError("descendant radius must be nonnegative")
    if kind == "plane":
        f = plane_guard(node_center, normal, offset)
        n = tuple(map(Phi.of, normal))
        return f.sign() > 0 and f * f > R * R * _dot(n, n)
    if kind == "sphere":
        radius = Phi.of(radius)
        if radius.sign() <= 0:
            raise DomainError("positive sphere radius required")
        return sphere_guard(node_center, center, radius + R).sign() > 0
    raise DomainError("no exclusion certificate for this primitive")


def eval_word(expression, environment, width):
    mask = (1 << width) - 1
    if type(expression) is int:
        if not 0 <= expression <= mask:
            raise DomainError("word literal outside width")
        return expression
    if isinstance(expression, str):
        if expression == "ones":
            return mask
        if expression not in environment:
            raise DomainError("unbound word name")
        return environment[expression] & mask
    if not isinstance(expression, (list, tuple)) or not expression:
        raise DomainError("explicit word AST required")
    op, *args = expression
    if op == "seq":
        if not args:
            raise DomainError("empty sequential word expression")
        value = eval_word(args[0], environment, width)
        for step in args[1:]:
            if not isinstance(step, (list, tuple)) or len(step) != 2 or step[0] not in ("and", "or", "xor"):
                raise DomainError("invalid left-fold word operation")
            rhs = eval_word(step[1], environment, width)
            value = value & rhs if step[0] == "and" else value | rhs if step[0] == "or" else value ^ rhs
        return value & mask
    if op == "not" and len(args) == 1:
        return mask ^ eval_word(args[0], environment, width)
    if op in ("and", "or", "xor") and len(args) == 2:
        a, b = (eval_word(arg, environment, width) for arg in args)
        return a & b if op == "and" else a | b if op == "or" else a ^ b
    raise DomainError("unsupported word AST")


def asa_na(word, present, masks):
    a = word & masks["asa"] & present
    n = a & masks["na"]
    hits = (n & masks["boundary"]).bit_count()
    return {"asa": a, "na": n, "hits": hits, "output": 0 if hits else n}


@dataclass(frozen=True)
class StepResult:
    status: str
    state: dict
    trace: dict
    reason: str = ""


class Engine:
    """Atomic exact guard -> ordered masks -> accepted-event JK reference."""
    @property
    def seed(self):
        """An editable copy; construct a new Engine to admit a changed seed."""
        return copy.deepcopy(self._seed)

    @property
    def state(self):
        """A snapshot. Caller mutation cannot alter authoritative state."""
        return copy.deepcopy(self._state)

    def __init__(self, seed: dict, state: dict | None = None):
        self._seed = copy.deepcopy(seed)
        self._validate_seed()
        self._state = copy.deepcopy(state) if state is not None else {
            "q": seed.get("q0", 0), "orientation": 0, "winding": 0,
            "branch_parity": 0, "last_side": None, "last_value": None,
            "step": 0, "last_sequence": -1, "events": []}
        self._validate_state()
        self._events = {item["id"]: item["request"] for item in self._state["events"]}

    def _validate_seed(self):
        s = self._seed
        if s.get("profile") != PROFILE:
            raise ValueError("not an ATOMOS-HINGE-R1 seed")
        width = s.get("width", 32)
        if type(width) is not int or not 1 <= width <= 4096:
            raise ValueError("word width outside declared 1..4096 limit")
        self.width, self.word_mask = width, (1 << width) - 1
        self.present = s.get("present", self.word_mask)
        if type(self.present) is not int or not 0 <= self.present <= self.word_mask:
            raise ValueError("invalid present mask")
        masks = s.get("masks")
        if not isinstance(masks, list) or len(masks) != 2:
            raise ValueError("exactly two independently stored mask sets required")
        for item in masks:
            if set(item) != {"asa", "na", "boundary"} or any(type(v) is not int or not 0 <= v <= self.word_mask for v in item.values()):
                raise ValueError("invalid mask fields")
        lane = s.get("drive_lane", 0)
        if type(lane) is not int or not 0 <= lane < width or not (self.present & (1 << lane)):
            raise ValueError("drive lane must be present")
        seam_lane = s.get("seam_lane")
        if seam_lane is not None and (type(seam_lane) is not int or not 0 <= seam_lane < width
                                     or seam_lane == lane or not self.present & (1 << seam_lane)):
            raise ValueError("seam lane must be present and disjoint")
        if s.get("boundary", "hold") not in ("hold", "inside", "outside"):
            raise ValueError("explicit supported boundary ownership required")
        if type(s.get("pulse_on_first", False)) is not bool:
            raise ValueError("pulse_on_first must be Boolean")
        if type(s.get("q0", 0)) is not int or s.get("q0", 0) < 0 or s.get("q0", 0) & ~self.present:
            raise ValueError("initial word outside present mask")
        self._nodes = {}
        for node in s.get("nodes", []):
            if not isinstance(node, dict) or not isinstance(node.get("id"), str) or not isinstance(node.get("op"), str):
                raise ValueError("typed node record required")
            if node["id"] in self._nodes or any(ref not in self._nodes for ref in node.get("args", [])):
                raise ValueError("duplicate/forward/cyclic graph reference")
            self._nodes[node["id"]] = node
        if not 0 < len(self._nodes) <= 4096 or s.get("guard") not in self._nodes:
            raise ValueError("guard export or declared node resource limit")
        for name in ("x", "j", "k"):
            if name not in s.get("equations", {}):
                raise ValueError("all word equations required")
        # Parse both phases under their legal binding names without executing a
        # transition. E_X cannot read y from the future stage.
        eval_word(s["equations"]["x"], {"q": 0, "d": 0, "e": 0}, width)
        for name in ("j", "k"):
            eval_word(s["equations"][name], {"q": 0, "d": 0, "e": 0, "y": 0}, width)
        canonical_bytes(s)

    def _validate_state(self):
        expected = {"q", "orientation", "winding", "branch_parity", "last_side", "last_value", "step", "last_sequence", "events"}
        if set(self._state) != expected:
            raise ValueError("state schema mismatch")
        s = self._state
        if type(s["q"]) is not int or s["q"] < 0 or s["q"] & ~self.present:
            raise ValueError("invalid state word")
        if (type(s["orientation"]) is not int or type(s["branch_parity"]) is not int
                or s["orientation"] not in (0, 1) or s["branch_parity"] not in (0, 1)
                or (s["last_side"] is not None and (type(s["last_side"]) is not int or s["last_side"] not in (-1, 0, 1)))):
            raise ValueError("invalid state bit/side")
        if any(type(s[k]) is not int for k in ("winding", "step", "last_sequence")) or s["step"] < 0 or s["last_sequence"] < -1:
            raise ValueError("invalid state counter")
        if s["last_value"] is not None and not isinstance(s["last_value"], Phi):
            raise ValueError("invalid exact state guard")
        if not isinstance(s["events"], list) or len(s["events"]) != s["step"]:
            raise ValueError("consumed event count mismatch")
        ids = set()
        for item in s["events"]:
            if (not isinstance(item, dict) or set(item) != {"id", "request"}
                    or not isinstance(item["id"], str) or not item["id"] or item["id"] in ids
                    or not isinstance(item["request"], str)):
                raise ValueError("invalid consumed identity")
            request = bytes.fromhex(item["request"])
            if request.hex() != item["request"]:
                raise ValueError("noncanonical consumed request hex")
            decoded = _decode(json.loads(request.decode("ascii"), object_pairs_hook=_no_duplicates))
            if (not isinstance(decoded, dict) or set(decoded) != {"sample", "crossing", "seam", "sequence"}
                    or canonical_bytes(decoded) != request):
                raise ValueError("invalid consumed request record")
            ids.add(item["id"])

    def evaluate(self, sample=None) -> Value:
        sample = {} if sample is None else sample
        memo = {}

        def visit(identity):
            if identity in memo:
                return memo[identity]
            node = self._nodes[identity]
            op, refs = node["op"], node.get("args", [])
            if op == "if":
                if len(refs) != 3:
                    raise DomainError("if arity")
                condition = visit(refs[0])
                if condition.frame is not None or condition.dimension != DIMLESS or condition.data not in (Phi(0), Phi(1)):
                    raise DomainError("if requires exact Boolean scalar 0 or 1")
                result = visit(refs[1] if condition.data == Phi(1) else refs[2])
            elif op in ("literal", "input"):
                typ = node.get("type", {})
                if op == "input":
                    key = node.get("key", identity)
                    if key not in sample:
                        raise MissingInput(key)
                    data = sample[key]
                else:
                    data = node["value"]
                if typ.get("kind") == "scalar":
                    if typ.get("frame") is not None:
                        raise DomainError("scalar cannot hide a coordinate frame")
                    result = _scalar(data, typ.get("dim"))
                elif typ.get("kind") == "vec3":
                    result = _vector(data, typ.get("dim"), typ.get("frame"))
                else:
                    raise DomainError("unsupported declared value type")
            else:
                args = [visit(ref) for ref in refs]
                result = operate(op, args, node)
            memo[identity] = result
            return result

        def operate(op, args, node):
            if op == "affine_point":
                if len(args) != 4:
                    raise DomainError("affine_point requires origin, velocity, time, epoch")
                p, v, t, epoch = args
                if (p.primitive != "vec3" or v.primitive != "vec3" or p.frame != v.frame
                        or t.dimension != TIME or epoch.dimension != TIME or t.frame is not None or epoch.frame is not None
                        or tuple(a + b for a, b in zip(v.dimension, TIME)) != p.dimension):
                    raise DomainError("affine motion frame/dimension mismatch")
                return _vector([x + rate * (t.data - epoch.data) for x, rate in zip(p.data, v.data)], p.dimension, p.frame)
            if op == "plane_guard":
                if len(args) != 3:
                    raise DomainError("plane_guard arity")
                point, normal, offset = args
                if (point.primitive != "vec3" or point.dimension != LENGTH or normal.primitive != "vec3" or point.frame != normal.frame
                        or normal.dimension != DIMLESS or offset.frame is not None or offset.dimension != point.dimension):
                    raise DomainError("plane frame/dimension mismatch")
                unit = _dot(normal.data, normal.data) == Phi(1)
                if node.get("require_sdf", False) and not unit:
                    raise DomainError("unit normal required for plane SDF")
                return Value(plane_guard(point.data, normal.data, offset.data), point.dimension,
                             primitive="plane_guard", is_sdf=unit)
            if op == "sphere_guard":
                if len(args) != 3:
                    raise DomainError("sphere_guard arity")
                point, center, radius = args
                _same_geometry(point, center)
                if point.dimension != LENGTH or radius.frame is not None or radius.dimension != point.dimension:
                    raise DomainError("radius dimension mismatch")
                return Value(sphere_guard(point.data, center.data, radius.data),
                             tuple(2 * d for d in point.dimension), primitive="sphere_sign_polynomial", is_sdf=False)
            if op in ("add", "sub", "mul", "div"):
                if len(args) != 2 or any(a.frame is not None or not isinstance(a.data, Phi) for a in args):
                    raise DomainError("scalar binary operation required")
                a, b = args
                if op in ("add", "sub"):
                    if a.dimension != b.dimension:
                        raise DomainError("add/sub unit mismatch")
                    data = a.data + b.data if op == "add" else a.data - b.data
                    return _scalar(data, a.dimension)
                dimension = tuple(x + y if op == "mul" else x - y for x, y in zip(a.dimension, b.dimension))
                return _scalar(a.data * b.data if op == "mul" else a.data / b.data, dimension)
            if op == "neg" and len(args) == 1 and isinstance(args[0].data, Phi):
                return _scalar(-args[0].data, args[0].dimension)
            if op == "sequence":
                operations = node.get("operations", [])
                if len(args) != len(operations) + 1 or not args:
                    raise DomainError("explicit left-fold operation count")
                result = args[0]
                for operation, argument in zip(operations, args[1:]):
                    if operation not in ("add", "sub", "mul", "div"):
                        raise DomainError("unsupported sequential operation")
                    result = operate(operation, [result, argument], {})
                return result
            raise UnsupportedOperation("retained unsupported operator: " + op)

        result = visit(self._seed["guard"])
        if not isinstance(result.data, Phi):
            raise DomainError("guard export must be exact scalar")
        return result

    def step(self, event_id: str, sample=None, *, crossing=None, seam=None, sequence=None) -> StepResult:
        trace = {}
        try:
            if not isinstance(event_id, str) or not event_id:
                raise ValueError("nonempty immutable event identity required")
            if crossing is not None and type(crossing) is not bool:
                raise ValueError("crossing must be Boolean or automatic")
            request = canonical_bytes({"sample": {} if sample is None else sample, "crossing": crossing,
                                       "seam": seam, "sequence": sequence}).hex()
            if event_id in self._events:
                if self._events[event_id] != request:
                    raise ValueError("same event identity with altered bytes/bindings")
                return StepResult("DUPLICATE", copy.deepcopy(self._state), {"accepted_event": False})
            logical_sequence = self._state["last_sequence"] + 1 if sequence is None else sequence
            if type(logical_sequence) is not int or logical_sequence <= self._state["last_sequence"]:
                raise ValueError("out-of-order event sequence")
            guard = self.evaluate(sample)
            parity, winding_delta = 0, 0
            if seam is not None:
                if not isinstance(seam, dict) or set(seam) != {"parity", "winding_delta", "source_value"}:
                    raise ValueError("seam requires parity, winding_delta and same-point source_value")
                parity, winding_delta = seam["parity"], seam["winding_delta"]
                if type(parity) is not int or parity not in (0, 1) or type(winding_delta) is not int:
                    raise ValueError("invalid seam parity/winding")
                if guard.data != ((-1) ** parity) * Phi.of(seam["source_value"]):
                    raise DomainError("signed-field gluing identity failed")
            seam_event = seam is not None and bool(parity or winding_delta)
            if seam_event and crossing is False:
                raise DomainError("declared seam transition cannot suppress its event")
            orientation = self._state["orientation"] ^ parity
            corrected = ((-1) ** orientation) * guard.data
            side = corrected.sign()
            trace = {"guard": guard.data, "corrected_guard": corrected, "sign": side,
                     "dimension": guard.dimension, "primitive": guard.primitive, "is_sdf": guard.is_sdf}
            if side == 0 and self._seed.get("boundary", "hold") == "hold":
                return StepResult("BOUNDARY", copy.deepcopy(self._state), trace, "explicit boundary hold; no commit")
            inside = side < 0 or (side == 0 and self._seed.get("boundary") == "inside")
            h = (self._state["last_side"] is not None and side != 0 and side != self._state["last_side"])
            if self._state["last_side"] is None:
                h = bool(self._seed.get("pulse_on_first", False))
            if crossing is not None:
                h = crossing
            h = bool(h or seam_event)
            drive_mask = 1 << self._seed.get("drive_lane", 0)
            drive, event_word = drive_mask if inside else 0, drive_mask if h else 0
            old_q = self._state["q"]
            env = {"q": old_q, "d": drive, "e": event_word}
            x = eval_word(self._seed["equations"]["x"], env, self.width)
            first = asa_na(x, self.present, self._seed["masks"][0])
            second = asa_na(first["output"], self.present, self._seed["masks"][1])
            env["y"] = second["output"]
            J = eval_word(self._seed["equations"]["j"], env, self.width)
            K = eval_word(self._seed["equations"]["k"], env, self.width)
            seam_lane = self._seed.get("seam_lane")
            if seam_lane is not None:
                seam_mask = 1 << seam_lane
                pulse = seam_mask if h and parity else 0
                J, K = (J & ~seam_mask) | pulse, (K & ~seam_mask) | pulse
            next_q = ((J & (self.word_mask ^ old_q)) | ((self.word_mask ^ K) & old_q)) & self.present
            new_state = copy.deepcopy(self._state)
            new_state.update(q=next_q, orientation=orientation, winding=self._state["winding"] + winding_delta,
                             branch_parity=self._state["branch_parity"] ^ int(h), last_value=guard.data,
                             step=self._state["step"] + 1, last_sequence=logical_sequence)
            if side != 0:
                new_state["last_side"] = side
            new_state["events"].append({"id": event_id, "request": request})
            trace.update(before=old_q, drive=drive, x=x, stages=[first, second], output=second["output"],
                         j=J, k=K, after=next_q, accepted_event=h, seam_parity=parity,
                         orientation_before=self._state["orientation"], orientation_after=orientation)
            self._state, self._events[event_id] = new_state, request
            return StepResult("VALUE", copy.deepcopy(new_state), trace)
        except MissingInput as error:
            return StepResult("MISSING_INPUT", copy.deepcopy(self._state), trace, str(error))
        except UnsupportedOperation as error:
            return StepResult("UNKNOWN", copy.deepcopy(self._state), trace, str(error))
        except DomainError as error:
            return StepResult("UNDEFINED", copy.deepcopy(self._state), trace, str(error))
        except RecursionError:
            return StepResult("RESOURCE_LIMIT", copy.deepcopy(self._state), trace, "graph recursion resource limit")
        except (ValueError, TypeError, KeyError, IndexError) as error:
            return StepResult("INVALID", copy.deepcopy(self._state), trace, str(error))

    def pack(self) -> bytes:
        return pack_document({"profile": PROFILE, "seed": self._seed, "state": self._state})

    @classmethod
    def unpack(cls, blob: bytes) -> "Engine":
        document = unpack_document(blob)
        if set(document) != {"profile", "seed", "state"} or document["profile"] != PROFILE:
            raise ValueError("invalid engine envelope schema")
        return cls(document["seed"], document["state"])

    def upload_words(self, word_bits=64) -> dict:
        """Byte-exact upload representation; never a floating geometry projection."""
        if word_bits not in (32, 64):
            raise ValueError("upload words are 32 or 64 bits")
        blob, size = self.pack(), word_bits // 8
        padded = blob + bytes((-len(blob)) % size)
        return {"profile": "ATOMOS-HINGE-UPLOAD-R1", "encoding": "little-endian-envelope-words",
                "word_bits": word_bits, "byte_length": len(blob), "sha256": hashlib.sha256(blob).hexdigest(),
                "words": tuple(int.from_bytes(padded[i:i + size], "little") for i in range(0, len(padded), size)),
                "geometry_projection": None}


def make_guard_seed(kind="plane", *, point=(0, 0, 0), velocity=None,
                    normal=(1, 0, 0), offset=0, center=(0, 0, 0), radius=1,
                    frame="world", width=32, drive_lane=0, seam_lane=None,
                    boundary="hold", pulse_on_first=False) -> dict:
    """Small inspectable builder. Input samples contain 'point', or 'time' for motion."""
    if type(width) is not int or not 1 <= width <= 4096:
        raise ValueError("word width outside declared 1..4096 limit")
    def node(identity, value, dimension, vector=False):
        return {"id": identity, "op": "literal", "value": list(value) if vector else value,
                "type": {"kind": "vec3" if vector else "scalar", "dim": list(dimension),
                         **({"frame": frame} if vector else {})}}
    nodes = []
    if velocity is None:
        nodes.append({"id": "point", "op": "input", "key": "point",
                      "type": {"kind": "vec3", "dim": list(LENGTH), "frame": frame}})
    else:
        nodes += [node("origin", point, LENGTH, True), node("velocity", velocity, VELOCITY, True),
                  {"id": "time", "op": "input", "type": {"kind": "scalar", "dim": list(TIME)}},
                  node("epoch", 0, TIME), {"id": "point", "op": "affine_point", "args": ["origin", "velocity", "time", "epoch"]}]
    if kind == "plane":
        nodes += [node("normal", normal, DIMLESS, True), node("offset", offset, LENGTH),
                  {"id": "guard", "op": "plane_guard", "args": ["point", "normal", "offset"]}]
    elif kind == "sphere":
        nodes += [node("center", center, LENGTH, True), node("radius", radius, LENGTH),
                  {"id": "guard", "op": "sphere_guard", "args": ["point", "center", "radius"]}]
    else:
        raise ValueError("builder supports plane or sphere")
    mask = (1 << width) - 1
    return {"profile": PROFILE, "width": width, "present": mask, "q0": 0,
            "nodes": nodes, "guard": "guard", "drive_lane": drive_lane, "seam_lane": seam_lane,
            "masks": [{"asa": mask, "na": mask, "boundary": 0} for _ in range(2)],
            "equations": {"x": "d", "j": ["and", "e", "y"], "k": ["and", "e", ["not", "y"]]},
            "boundary": boundary, "pulse_on_first": pulse_on_first,
            "provenance": {"meaning": "exact nominal coordinates; no physical calibration inferred"}}
