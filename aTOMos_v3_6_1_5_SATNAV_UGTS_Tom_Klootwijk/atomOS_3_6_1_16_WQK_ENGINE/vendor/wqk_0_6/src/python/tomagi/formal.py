"""Bounded evaluation of content-addressed, JSON-native formal programs.

The language in this module is deliberately small and domain-neutral.  A
program is an expression tree, not host code: it has no recursion, function
calls, or open-ended loop construct.  Repetition is limited to finite input
lists and is guarded by host-supplied limits.

Exact rationals use the canonical JSON record ``{"num": n, "den": d}``, where
``n`` and ``d`` are integers, ``d`` is positive, and the fraction is reduced.
Arithmetic operations always return that representation.  Plain JSON integers
remain useful for list indexes and may also be used as exact numeric operands.
The ``unique`` operation identifies values by canonical JSON bytes and preserves
the first occurrence in the finite source list.
"""

from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
import copy
import hashlib
import json
import math
from typing import Any, Mapping


PROGRAM_SCHEMA = "TOMAGI-FORMAL-PROGRAM-1.0"
RESULT_SCHEMA = "TOMAGI-FORMAL-RESULT-1.0"

OPERATIONS = frozenset({
    "lit", "rat", "ref", "list", "record", "let",
    "get", "has", "keys", "values", "put", "merge", "len", "is_string", "concat", "append",
    "add", "sub", "mul", "div", "neg", "abs", "floor", "integer_abs", "bit_length",
    "eq", "ne", "lt", "le", "gt", "ge", "not", "and", "or",
    "if", "assert", "hash",
    "pairs", "unique", "map", "filter", "sort", "group", "fold",
})


class FormalError(ValueError):
    """Base class for formal-program validation and evaluation failures."""


class FormalValidationError(FormalError):
    """The program or a JSON value is outside the formal data model."""


class FormalEvaluationError(FormalError):
    """A well-formed operation cannot be evaluated for the supplied values."""


class FormalBudgetExceeded(FormalEvaluationError):
    """Evaluation exceeded a host-defined finite resource limit."""


class FormalAssertionError(FormalEvaluationError):
    """A formal ``assert`` expression evaluated to false."""


@dataclass(frozen=True)
class Limits:
    """Host-side limits; a literal program cannot relax these values."""

    max_steps: int = 100_000
    max_depth: int = 128
    max_collection_items: int = 10_000
    max_value_nodes: int = 100_000
    max_canonical_bytes: int = 4_000_000

    def __post_init__(self) -> None:
        for name in (
            "max_steps",
            "max_depth",
            "max_collection_items",
            "max_value_nodes",
            "max_canonical_bytes",
        ):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value <= 0:
                raise FormalValidationError(f"{name} must be a positive integer")


def _is_int(value: Any) -> bool:
    return isinstance(value, int) and not isinstance(value, bool)


def _is_rational(value: Any) -> bool:
    return (
        isinstance(value, dict)
        and set(value) == {"num", "den"}
        and _is_int(value.get("num"))
        and _is_int(value.get("den"))
    )


def _looks_rational(value: Any) -> bool:
    return isinstance(value, dict) and set(value) == {"num", "den"}


def _validate_rational(value: Mapping[str, Any], path: str) -> None:
    num = value["num"]
    den = value["den"]
    if not _is_int(num) or not _is_int(den):
        raise FormalValidationError(f"{path}: rational numerator and denominator must be integers")
    if den <= 0:
        raise FormalValidationError(f"{path}: rational denominator must be positive")
    if math.gcd(abs(num), den) != 1:
        raise FormalValidationError(f"{path}: rational must be reduced")
    if num == 0 and den != 1:
        raise FormalValidationError(f"{path}: zero rational must have denominator 1")


def rational(num: int, den: int = 1) -> dict[str, int]:
    """Return a reduced exact-rational JSON record."""

    if not _is_int(num) or not _is_int(den):
        raise FormalValidationError("rational numerator and denominator must be integers")
    if den == 0:
        raise FormalEvaluationError("division by zero")
    fraction = Fraction(num, den)
    return {"num": fraction.numerator, "den": fraction.denominator}


def _validate_json(value: Any, limits: Limits, *, path: str = "$", depth: int = 0,
                   counter: list[int] | None = None) -> None:
    if counter is None:
        counter = [0]
    counter[0] += 1
    if counter[0] > limits.max_value_nodes:
        raise FormalBudgetExceeded(
            f"JSON value exceeds max_value_nodes={limits.max_value_nodes}"
        )
    if depth > limits.max_depth:
        raise FormalBudgetExceeded(f"JSON value exceeds max_depth={limits.max_depth}")

    if value is None or isinstance(value, (bool, str)) or _is_int(value):
        return
    if isinstance(value, float):
        raise FormalValidationError(f"{path}: floating-point values are forbidden")
    if isinstance(value, list):
        if len(value) > limits.max_collection_items:
            raise FormalBudgetExceeded(
                f"{path}: list exceeds max_collection_items={limits.max_collection_items}"
            )
        for index, item in enumerate(value):
            _validate_json(item, limits, path=f"{path}[{index}]", depth=depth + 1,
                           counter=counter)
        return
    if isinstance(value, dict):
        if len(value) > limits.max_collection_items:
            raise FormalBudgetExceeded(
                f"{path}: record exceeds max_collection_items={limits.max_collection_items}"
            )
        for key in value:
            if not isinstance(key, str):
                raise FormalValidationError(f"{path}: record keys must be strings")
        if _looks_rational(value):
            _validate_rational(value, path)
        for key in sorted(value):
            _validate_json(value[key], limits, path=f"{path}.{key}", depth=depth + 1,
                           counter=counter)
        return
    raise FormalValidationError(
        f"{path}: value of type {type(value).__name__} is not JSON-native"
    )


def canonical_bytes(value: Any, *, limits: Limits | None = None) -> bytes:
    """Validate and serialize a formal value to deterministic canonical JSON."""

    active = limits or Limits()
    _validate_json(value, active)
    data = json.dumps(
        value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    if len(data) > active.max_canonical_bytes:
        raise FormalBudgetExceeded(
            f"canonical value exceeds max_canonical_bytes={active.max_canonical_bytes}"
        )
    return data


def content_address(value: Any, *, limits: Limits | None = None) -> str:
    """Return the canonical SHA-256 address of a formal JSON value."""

    return "sha256:" + hashlib.sha256(canonical_bytes(value, limits=limits)).hexdigest()


def program_content_hash(program: Mapping[str, Any], *, limits: Limits | None = None) -> str:
    """Hash a program record while excluding its self-address field."""

    if not isinstance(program, Mapping):
        raise FormalValidationError("program must be a record")
    body = {key: copy.deepcopy(value) for key, value in program.items()
            if key != "content_hash"}
    return content_address(body, limits=limits)


def attach_program_hash(program: Mapping[str, Any], *, limits: Limits | None = None) -> dict[str, Any]:
    """Return a detached program record with its canonical content address."""

    out = copy.deepcopy(dict(program))
    out["content_hash"] = program_content_hash(out, limits=limits)
    return out


def verify_program_hash(program: Mapping[str, Any], *, limits: Limits | None = None) -> bool:
    """Return whether a program carries its exact canonical content address."""

    claimed = program.get("content_hash") if isinstance(program, Mapping) else None
    return isinstance(claimed, str) and claimed == program_content_hash(program, limits=limits)


def make_program(expression: Mapping[str, Any], *, program_id: str | None = None,
                 limits: Limits | None = None) -> dict[str, Any]:
    """Construct and content-address a formal program record."""

    active = limits or Limits()
    canonical_bytes(expression, limits=active)
    _validate_expression_syntax(expression, active)
    record: dict[str, Any] = {"schema": PROGRAM_SCHEMA, "expression": copy.deepcopy(expression)}
    if program_id is not None:
        if not isinstance(program_id, str) or not program_id:
            raise FormalValidationError("program_id must be a non-empty string")
        record["id"] = program_id
    return attach_program_hash(record, limits=active)


def _as_fraction(value: Any, context: str) -> Fraction:
    if _is_int(value):
        return Fraction(value, 1)
    if _is_rational(value):
        _validate_rational(value, context)
        return Fraction(value["num"], value["den"])
    raise FormalEvaluationError(f"{context} requires an exact integer or rational")


def _from_fraction(value: Fraction) -> dict[str, int]:
    return {"num": value.numerator, "den": value.denominator}


def _require_bool(value: Any, context: str) -> bool:
    if not isinstance(value, bool):
        raise FormalEvaluationError(f"{context} requires a boolean")
    return value


def _total_key(value: Any) -> tuple[Any, ...]:
    """A deterministic total order over validated formal JSON values."""

    if value is None:
        return (0,)
    if isinstance(value, bool):
        return (1, int(value))
    if _is_int(value):
        fraction = Fraction(value, 1)
        return (2, fraction)
    if _is_rational(value):
        fraction = _as_fraction(value, "sort key")
        return (2, fraction)
    if isinstance(value, str):
        return (3, value)
    if isinstance(value, list):
        return (4, tuple(_total_key(item) for item in value))
    if isinstance(value, dict):
        return (5, tuple((key, _total_key(value[key])) for key in sorted(value)))
    raise FormalEvaluationError("sort key is not a formal JSON value")


def _strict_fields(expression: Mapping[str, Any], required: set[str],
                   optional: set[str] | None = None) -> None:
    permitted = required | (optional or set()) | {"op"}
    missing = sorted(required - set(expression))
    extra = sorted(set(expression) - permitted)
    if missing:
        raise FormalValidationError(f"operation {expression.get('op')!r} missing fields: {missing}")
    if extra:
        raise FormalValidationError(f"operation {expression.get('op')!r} has unknown fields: {extra}")


def _binding_name(value: Any, field: str) -> str:
    if not isinstance(value, str) or not value:
        raise FormalValidationError(f"{field} must be a non-empty binding name")
    return value


def _validate_expression_syntax(expression: Any, limits: Limits, depth: int = 0) -> None:
    """Validate the complete expression tree, including unreachable branches."""

    if depth > limits.max_depth:
        raise FormalBudgetExceeded(f"expression exceeds max_depth={limits.max_depth}")
    if not isinstance(expression, dict):
        raise FormalValidationError("every expression must be an operation record")
    operation = expression.get("op")
    if not isinstance(operation, str):
        raise FormalValidationError("expression op must be a string")
    if operation not in OPERATIONS:
        hint = " (unbounded loops are not supported)" if operation in {"while", "loop"} else ""
        raise FormalValidationError(f"unknown formal operation {operation!r}{hint}")

    children: list[Any] = []
    if operation == "lit":
        _strict_fields(expression, {"value"})
    elif operation == "rat":
        _strict_fields(expression, {"num", "den"})
        children = [expression["num"], expression["den"]]
    elif operation == "ref":
        _strict_fields(expression, {"name"})
        _binding_name(expression["name"], "ref name")
    elif operation == "list":
        _strict_fields(expression, {"items"})
        if not isinstance(expression["items"], list):
            raise FormalValidationError("list items must be an expression list")
        children = list(expression["items"])
    elif operation == "record":
        _strict_fields(expression, {"fields"})
        fields = expression["fields"]
        if not isinstance(fields, dict) or any(not isinstance(key, str) for key in fields):
            raise FormalValidationError("record fields must be a string-keyed expression record")
        children = [fields[key] for key in sorted(fields)]
    elif operation == "let":
        _strict_fields(expression, {"bindings", "body"})
        bindings = expression["bindings"]
        if not isinstance(bindings, list):
            raise FormalValidationError("let bindings must be an ordered list")
        names: set[str] = set()
        for binding in bindings:
            if not isinstance(binding, dict) or set(binding) != {"name", "value"}:
                raise FormalValidationError("each let binding requires only name and value")
            name = _binding_name(binding["name"], "let binding name")
            if name in names:
                raise FormalValidationError(f"duplicate let binding {name!r}")
            names.add(name)
            children.append(binding["value"])
        children.append(expression["body"])
    elif operation in {"get", "has"}:
        _strict_fields(expression, {"target", "key"})
        children = [expression["target"], expression["key"]]
    elif operation in {"keys", "values"}:
        _strict_fields(expression, {"target"})
        children = [expression["target"]]
    elif operation in {"len", "is_string", "neg", "abs", "floor", "integer_abs", "bit_length", "not", "hash"}:
        _strict_fields(expression, {"value"})
        children = [expression["value"]]
    elif operation in {
        "add", "sub", "mul", "div", "eq", "ne", "lt", "le", "gt", "ge",
        "concat", "merge",
    }:
        _strict_fields(expression, {"left", "right"})
        children = [expression["left"], expression["right"]]
    elif operation == "put":
        _strict_fields(expression, {"target", "key", "value"})
        children = [expression["target"], expression["key"], expression["value"]]
    elif operation == "append":
        _strict_fields(expression, {"source", "value"})
        children = [expression["source"], expression["value"]]
    elif operation in {"and", "or"}:
        _strict_fields(expression, {"values"})
        if not isinstance(expression["values"], list):
            raise FormalValidationError(f"{operation} values must be an expression list")
        children = list(expression["values"])
    elif operation == "if":
        _strict_fields(expression, {"condition", "then", "else"})
        children = [expression["condition"], expression["then"], expression["else"]]
    elif operation == "assert":
        _strict_fields(expression, {"condition", "value"}, {"message"})
        if "message" in expression and not isinstance(expression["message"], str):
            raise FormalValidationError("assert message must be a string")
        children = [expression["condition"], expression["value"]]
    elif operation in {"pairs", "unique"}:
        _strict_fields(expression, {"source"})
        children = [expression["source"]]
    elif operation in {"map", "filter", "sort", "group"}:
        body_field = {"map": "body", "filter": "predicate"}.get(operation, "key")
        optional = {"index", "descending"} if operation == "sort" else {"index"}
        _strict_fields(expression, {"source", "item", body_field}, optional)
        item = _binding_name(expression["item"], "item")
        index = expression.get("index")
        if index is not None:
            index = _binding_name(index, "index")
            if index == item:
                raise FormalValidationError("item and index bindings must be distinct")
        if operation == "sort" and not isinstance(expression.get("descending", False), bool):
            raise FormalValidationError("sort descending must be a boolean")
        children = [expression["source"], expression[body_field]]
    elif operation == "fold":
        _strict_fields(
            expression, {"source", "item", "accumulator", "initial", "body"}, {"index"}
        )
        item = _binding_name(expression["item"], "item")
        accumulator = _binding_name(expression["accumulator"], "accumulator")
        index = expression.get("index")
        if index is not None:
            index = _binding_name(index, "index")
        names = [name for name in (item, accumulator, index) if name is not None]
        if len(names) != len(set(names)):
            raise FormalValidationError("fold binding names must be distinct")
        children = [expression["source"], expression["initial"], expression["body"]]

    for child in children:
        _validate_expression_syntax(child, limits, depth + 1)


class _Evaluator:
    def __init__(self, limits: Limits):
        self.limits = limits
        self.steps = 0
        # Formal values are immutable by language contract.  Retaining each
        # validated compound object makes an identity cache safe against id
        # reuse while avoiding quadratic re-validation of large shared values.
        self._validated_objects: dict[int, Any] = {}

    def _check_result(self, value: Any) -> None:
        """Bound every recursive result before its parent consumes it.

        Scalars are cheap and are checked directly.  Lists/records are checked
        once per immutable object identity; the cache retains the object so a
        Python id cannot be reused during evaluation.  This preserves the
        CODEX repair invariant without repeatedly serializing the same large
        registry or candidate collection through nested ``ref``/``get`` nodes.
        """
        if value is None or isinstance(value, (bool, str)) or _is_int(value):
            _validate_json(value, self.limits)
            canonical_bytes(value, limits=self.limits)
            return
        identity = id(value)
        prior = self._validated_objects.get(identity)
        if prior is value:
            return
        _validate_json(value, self.limits)
        canonical_bytes(value, limits=self.limits)
        self._validated_objects[identity] = value

    def _charge(self, amount: int = 1) -> None:
        if amount < 0 or self.steps + amount > self.limits.max_steps:
            raise FormalBudgetExceeded(
                f"evaluation exceeds max_steps={self.limits.max_steps}"
            )
        self.steps += amount

    def _finite_source(self, value: Any, operation: str) -> list[Any]:
        if not isinstance(value, list):
            raise FormalEvaluationError(f"{operation} requires a list source")
        if len(value) > self.limits.max_collection_items:
            raise FormalBudgetExceeded(
                f"{operation} source exceeds max_collection_items="
                f"{self.limits.max_collection_items}"
            )
        return value

    @staticmethod
    def _binder(expression: Mapping[str, Any], field: str) -> str:
        name = expression[field]
        if not isinstance(name, str) or not name:
            raise FormalValidationError(f"{field} must be a non-empty binding name")
        return name

    def _child_scope(self, scope: Mapping[str, Any], values: Mapping[str, Any]) -> dict[str, Any]:
        out = dict(scope)
        out.update(values)
        return out

    def eval(self, expression: Any, scope: Mapping[str, Any], depth: int = 0) -> Any:
        value = self._eval_unchecked(expression, scope, depth)
        # Every recursive result is bounded before its parent can consume it.
        # This includes fold accumulators and map/filter/group intermediates.
        self._check_result(value)
        return value

    def _eval_unchecked(self, expression: Any, scope: Mapping[str, Any], depth: int = 0) -> Any:
        self._charge()
        if depth > self.limits.max_depth:
            raise FormalBudgetExceeded(
                f"expression exceeds max_depth={self.limits.max_depth}"
            )
        if not isinstance(expression, dict):
            raise FormalValidationError("every expression must be an operation record")
        operation = expression.get("op")
        if not isinstance(operation, str):
            raise FormalValidationError("expression op must be a string")

        child_depth = depth + 1

        if operation == "lit":
            _strict_fields(expression, {"value"})
            value = copy.deepcopy(expression["value"])
            _validate_json(value, self.limits)
            return value

        if operation == "rat":
            _strict_fields(expression, {"num", "den"})
            num = self.eval(expression["num"], scope, child_depth)
            den = self.eval(expression["den"], scope, child_depth)
            if not _is_int(num) or not _is_int(den):
                raise FormalEvaluationError("rat numerator and denominator must evaluate to integers")
            return rational(num, den)

        if operation == "ref":
            _strict_fields(expression, {"name"})
            name = expression["name"]
            if not isinstance(name, str) or not name:
                raise FormalValidationError("ref name must be a non-empty string")
            if name not in scope:
                raise FormalEvaluationError(f"unknown reference {name!r}")
            return scope[name]

        if operation == "list":
            _strict_fields(expression, {"items"})
            items = expression["items"]
            if not isinstance(items, list):
                raise FormalValidationError("list items must be an expression list")
            if len(items) > self.limits.max_collection_items:
                raise FormalBudgetExceeded("list constructor exceeds max_collection_items")
            return [self.eval(item, scope, child_depth) for item in items]

        if operation == "record":
            _strict_fields(expression, {"fields"})
            fields = expression["fields"]
            if not isinstance(fields, dict) or any(not isinstance(key, str) for key in fields):
                raise FormalValidationError("record fields must be a string-keyed expression record")
            if len(fields) > self.limits.max_collection_items:
                raise FormalBudgetExceeded("record constructor exceeds max_collection_items")
            value = {key: self.eval(fields[key], scope, child_depth) for key in sorted(fields)}
            _validate_json(value, self.limits)
            return value

        if operation == "let":
            _strict_fields(expression, {"bindings", "body"})
            bindings = expression["bindings"]
            if not isinstance(bindings, list):
                raise FormalValidationError("let bindings must be an ordered list")
            if len(bindings) > self.limits.max_collection_items:
                raise FormalBudgetExceeded("let bindings exceed max_collection_items")
            nested = dict(scope)
            names: set[str] = set()
            for binding in bindings:
                if not isinstance(binding, dict) or set(binding) != {"name", "value"}:
                    raise FormalValidationError("each let binding requires only name and value")
                name = binding["name"]
                if not isinstance(name, str) or not name:
                    raise FormalValidationError("let binding name must be a non-empty string")
                if name in names:
                    raise FormalValidationError(f"duplicate let binding {name!r}")
                nested[name] = self.eval(binding["value"], nested, child_depth)
                names.add(name)
            return self.eval(expression["body"], nested, child_depth)

        if operation == "get":
            _strict_fields(expression, {"target", "key"})
            target = self.eval(expression["target"], scope, child_depth)
            key = self.eval(expression["key"], scope, child_depth)
            if isinstance(target, list):
                if not _is_int(key) or key < 0 or key >= len(target):
                    raise FormalEvaluationError("list key must be an in-range non-negative integer")
                return target[key]
            if isinstance(target, dict):
                if not isinstance(key, str) or key not in target:
                    raise FormalEvaluationError("record key must name an existing field")
                return target[key]
            raise FormalEvaluationError("get target must be a list or record")

        if operation == "has":
            _strict_fields(expression, {"target", "key"})
            target = self.eval(expression["target"], scope, child_depth)
            key = self.eval(expression["key"], scope, child_depth)
            if isinstance(target, list):
                return _is_int(key) and 0 <= key < len(target)
            if isinstance(target, dict):
                return isinstance(key, str) and key in target
            raise FormalEvaluationError("has target must be a list or record")

        if operation == "keys":
            _strict_fields(expression, {"target"})
            target = self.eval(expression["target"], scope, child_depth)
            if not isinstance(target, dict):
                raise FormalEvaluationError("keys target must be a record")
            return sorted(target)

        if operation == "values":
            _strict_fields(expression, {"target"})
            target = self.eval(expression["target"], scope, child_depth)
            if not isinstance(target, dict):
                raise FormalEvaluationError("values target must be a record")
            return [target[key] for key in sorted(target)]

        if operation == "put":
            _strict_fields(expression, {"target", "key", "value"})
            target = self.eval(expression["target"], scope, child_depth)
            key = self.eval(expression["key"], scope, child_depth)
            if not isinstance(target, dict) or not isinstance(key, str):
                raise FormalEvaluationError("put requires a record and string key")
            out = dict(target)
            out[key] = self.eval(expression["value"], scope, child_depth)
            _validate_json(out, self.limits)
            return out

        if operation == "merge":
            _strict_fields(expression, {"left", "right"})
            left = self.eval(expression["left"], scope, child_depth)
            right = self.eval(expression["right"], scope, child_depth)
            if not isinstance(left, dict) or not isinstance(right, dict):
                raise FormalEvaluationError("merge requires two records")
            out = dict(left)
            for key in sorted(right):
                out[key] = right[key]
            _validate_json(out, self.limits)
            return out

        if operation == "len":
            _strict_fields(expression, {"value"})
            value = self.eval(expression["value"], scope, child_depth)
            if not isinstance(value, (list, dict, str)):
                raise FormalEvaluationError("len requires a list, record, or string")
            return len(value)

        if operation == "is_string":
            _strict_fields(expression, {"value"})
            return isinstance(self.eval(expression["value"], scope, child_depth), str)

        if operation == "concat":
            _strict_fields(expression, {"left", "right"})
            left = self._finite_source(self.eval(expression["left"], scope, child_depth), "concat")
            right = self._finite_source(self.eval(expression["right"], scope, child_depth), "concat")
            if len(left) + len(right) > self.limits.max_collection_items:
                raise FormalBudgetExceeded("concat result exceeds max_collection_items")
            self._charge(len(left) + len(right))
            return list(left) + list(right)

        if operation == "append":
            _strict_fields(expression, {"source", "value"})
            source = self._finite_source(self.eval(expression["source"], scope, child_depth), "append")
            if len(source) + 1 > self.limits.max_collection_items:
                raise FormalBudgetExceeded("append result exceeds max_collection_items")
            return list(source) + [self.eval(expression["value"], scope, child_depth)]

        if operation in {"add", "sub", "mul", "div"}:
            _strict_fields(expression, {"left", "right"})
            left = _as_fraction(self.eval(expression["left"], scope, child_depth), operation)
            right = _as_fraction(self.eval(expression["right"], scope, child_depth), operation)
            if operation == "add":
                result = left + right
            elif operation == "sub":
                result = left - right
            elif operation == "mul":
                result = left * right
            else:
                if right == 0:
                    raise FormalEvaluationError("division by zero")
                result = left / right
            return _from_fraction(result)

        if operation in {"neg", "abs"}:
            _strict_fields(expression, {"value"})
            value = _as_fraction(self.eval(expression["value"], scope, child_depth), operation)
            return _from_fraction(-value if operation == "neg" else abs(value))

        if operation == "floor":
            _strict_fields(expression, {"value"})
            value = _as_fraction(self.eval(expression["value"], scope, child_depth), operation)
            return value.numerator // value.denominator

        if operation == "integer_abs":
            _strict_fields(expression, {"value"})
            value = self.eval(expression["value"], scope, child_depth)
            if not _is_int(value):
                raise FormalEvaluationError("integer_abs requires an integer")
            return abs(value)

        if operation == "bit_length":
            _strict_fields(expression, {"value"})
            value = self.eval(expression["value"], scope, child_depth)
            if not _is_int(value) or value < 0:
                raise FormalEvaluationError("bit_length requires a non-negative integer")
            return value.bit_length()

        if operation in {"eq", "ne", "lt", "le", "gt", "ge"}:
            _strict_fields(expression, {"left", "right"})
            left = self.eval(expression["left"], scope, child_depth)
            right = self.eval(expression["right"], scope, child_depth)
            numeric = (_is_int(left) or _is_rational(left)) and (
                _is_int(right) or _is_rational(right)
            )
            if operation in {"eq", "ne"}:
                # Python considers ``True == 1`` and applies that coercion
                # recursively inside lists and dictionaries.  Formal JSON does
                # not: booleans and exact numbers are distinct value types.
                # Canonical bytes provide type-strict structural equality for
                # every non-numeric formal value while retaining rational
                # numeric equality in the branch above.
                equal = (
                    _as_fraction(left, operation) == _as_fraction(right, operation)
                    if numeric
                    else canonical_bytes(left, limits=self.limits)
                    == canonical_bytes(right, limits=self.limits)
                )
                return equal if operation == "eq" else not equal
            if not numeric:
                raise FormalEvaluationError(f"{operation} requires exact numeric operands")
            a = _as_fraction(left, operation)
            b = _as_fraction(right, operation)
            return {"lt": a < b, "le": a <= b, "gt": a > b, "ge": a >= b}[operation]

        if operation == "not":
            _strict_fields(expression, {"value"})
            return not _require_bool(self.eval(expression["value"], scope, child_depth), "not")

        if operation in {"and", "or"}:
            _strict_fields(expression, {"values"})
            values = expression["values"]
            if not isinstance(values, list):
                raise FormalValidationError(f"{operation} values must be an expression list")
            if len(values) > self.limits.max_collection_items:
                raise FormalBudgetExceeded(f"{operation} values exceed max_collection_items")
            identity = operation == "and"
            for child in values:
                value = _require_bool(self.eval(child, scope, child_depth), operation)
                if value != identity:
                    return value
            return identity

        if operation == "if":
            _strict_fields(expression, {"condition", "then", "else"})
            condition = _require_bool(
                self.eval(expression["condition"], scope, child_depth), "if"
            )
            branch = "then" if condition else "else"
            return self.eval(expression[branch], scope, child_depth)

        if operation == "assert":
            _strict_fields(expression, {"condition", "value"}, {"message"})
            message = expression.get("message", "formal assertion failed")
            if not isinstance(message, str):
                raise FormalValidationError("assert message must be a string")
            condition = _require_bool(
                self.eval(expression["condition"], scope, child_depth), "assert"
            )
            if not condition:
                raise FormalAssertionError(message)
            return self.eval(expression["value"], scope, child_depth)

        if operation == "hash":
            _strict_fields(expression, {"value"})
            value = self.eval(expression["value"], scope, child_depth)
            return content_address(value, limits=self.limits)

        if operation == "pairs":
            _strict_fields(expression, {"source"})
            source = self._finite_source(
                self.eval(expression["source"], scope, child_depth), "pairs"
            )
            count = len(source) * (len(source) - 1) // 2
            if count > self.limits.max_collection_items:
                raise FormalBudgetExceeded("pairs result exceeds max_collection_items")
            self._charge(count)
            return [
                {
                    "left": source[left],
                    "left_index": left,
                    "right": source[right],
                    "right_index": right,
                }
                for left in range(len(source))
                for right in range(left + 1, len(source))
            ]

        if operation == "unique":
            _strict_fields(expression, {"source"})
            source = self._finite_source(
                self.eval(expression["source"], scope, child_depth), "unique"
            )
            seen: set[bytes] = set()
            output: list[Any] = []
            for item in source:
                self._charge()
                identity = canonical_bytes(item, limits=self.limits)
                if identity not in seen:
                    seen.add(identity)
                    output.append(item)
            return output

        if operation in {"map", "filter", "sort", "group"}:
            required = {"source", "item", "body"} if operation == "map" else {
                "source", "item", "predicate"
            } if operation == "filter" else {"source", "item", "key"}
            _strict_fields(expression, required, {"index", "descending"} if operation == "sort"
                           else {"index"})
            source = self._finite_source(
                self.eval(expression["source"], scope, child_depth), operation
            )
            item_name = self._binder(expression, "item")
            index_name = expression.get("index")
            if index_name is not None and (not isinstance(index_name, str) or not index_name):
                raise FormalValidationError("index must be a non-empty binding name")
            if index_name == item_name:
                raise FormalValidationError("item and index bindings must be distinct")

            decorated: list[tuple[Any, Any]] = []
            output: list[Any] = []
            for index, item in enumerate(source):
                self._charge()
                values = {item_name: item}
                if index_name is not None:
                    values[index_name] = index
                nested = self._child_scope(scope, values)
                if operation == "map":
                    output.append(self.eval(expression["body"], nested, child_depth))
                elif operation == "filter":
                    keep = _require_bool(
                        self.eval(expression["predicate"], nested, child_depth), "filter"
                    )
                    if keep:
                        output.append(item)
                else:
                    key = self.eval(expression["key"], nested, child_depth)
                    _validate_json(key, self.limits)
                    decorated.append((key, item))

            if operation in {"map", "filter"}:
                if len(output) > self.limits.max_collection_items:
                    raise FormalBudgetExceeded(f"{operation} result exceeds max_collection_items")
                return output
            if operation == "sort":
                descending = expression.get("descending", False)
                if not isinstance(descending, bool):
                    raise FormalValidationError("sort descending must be a boolean")
                decorated.sort(key=lambda pair: _total_key(pair[0]), reverse=descending)
                return [item for _, item in decorated]

            groups: dict[bytes, tuple[Any, list[Any]]] = {}
            for key, item in decorated:
                encoded = canonical_bytes(key, limits=self.limits)
                if encoded not in groups:
                    groups[encoded] = (key, [])
                groups[encoded][1].append(item)
            ordered = sorted(groups.values(), key=lambda group: _total_key(group[0]))
            return [{"key": key, "items": items} for key, items in ordered]

        if operation == "fold":
            _strict_fields(
                expression,
                {"source", "item", "accumulator", "initial", "body"},
                {"index"},
            )
            source = self._finite_source(
                self.eval(expression["source"], scope, child_depth), "fold"
            )
            item_name = self._binder(expression, "item")
            accumulator_name = self._binder(expression, "accumulator")
            index_name = expression.get("index")
            names = [name for name in (item_name, accumulator_name, index_name) if name is not None]
            if len(names) != len(set(names)):
                raise FormalValidationError("fold binding names must be distinct")
            if index_name is not None and (not isinstance(index_name, str) or not index_name):
                raise FormalValidationError("index must be a non-empty binding name")
            accumulator = self.eval(expression["initial"], scope, child_depth)
            for index, item in enumerate(source):
                self._charge()
                values = {item_name: item, accumulator_name: accumulator}
                if index_name is not None:
                    values[index_name] = index
                accumulator = self.eval(
                    expression["body"], self._child_scope(scope, values), child_depth
                )
            return accumulator

        hint = " (unbounded loops are not supported)" if operation in {"while", "loop"} else ""
        raise FormalValidationError(f"unknown formal operation {operation!r}{hint}")


def evaluate_with_steps(expression: Mapping[str, Any],
                        bindings: Mapping[str, Any] | None = None, *,
                        limits: Limits | None = None) -> dict[str, Any]:
    """Evaluate an expression and return its detached value and exact step count."""

    active = limits or Limits()
    scope = copy.deepcopy(dict(bindings or {}))
    if any(not isinstance(name, str) or not name for name in scope):
        raise FormalValidationError("binding names must be non-empty strings")
    canonical_bytes(scope, limits=active)
    canonical_bytes(expression, limits=active)
    _validate_expression_syntax(expression, active)
    evaluator = _Evaluator(active)
    value = evaluator.eval(expression, scope)
    _validate_json(value, active)
    canonical_bytes(value, limits=active)
    return {"value": copy.deepcopy(value), "steps": evaluator.steps}


def evaluate(expression: Mapping[str, Any], bindings: Mapping[str, Any] | None = None,
             *, limits: Limits | None = None) -> Any:
    """Evaluate an expression and return a detached JSON-native value."""

    return evaluate_with_steps(expression, bindings, limits=limits)["value"]


def run_program(program: Mapping[str, Any], inputs: Mapping[str, Any] | None = None,
                *, limits: Limits | None = None) -> dict[str, Any]:
    """Verify and run a content-addressed program, returning an addressed result.

    The integration boundary is intentionally JSON-only: ``program`` and
    ``inputs`` are records, and the returned result is a canonical record with
    its own ``content_hash``.
    """

    active = limits or Limits()
    if not isinstance(program, Mapping):
        raise FormalValidationError("program must be a record")
    allowed = {"schema", "id", "expression", "content_hash"}
    missing = {"schema", "expression", "content_hash"} - set(program)
    extra = set(program) - allowed
    if missing:
        raise FormalValidationError(f"program missing fields: {sorted(missing)}")
    if extra:
        raise FormalValidationError(f"program has unknown fields: {sorted(extra)}")
    if program["schema"] != PROGRAM_SCHEMA:
        raise FormalValidationError(f"unsupported program schema {program['schema']!r}")
    if "id" in program and (not isinstance(program["id"], str) or not program["id"]):
        raise FormalValidationError("program id must be a non-empty string")
    _validate_json(dict(program), active)
    if not verify_program_hash(program, limits=active):
        raise FormalValidationError("program content hash mismatch")
    _validate_expression_syntax(program["expression"], active)

    scope = copy.deepcopy(dict(inputs or {}))
    if any(not isinstance(name, str) or not name for name in scope):
        raise FormalValidationError("input names must be non-empty strings")
    canonical_bytes(scope, limits=active)
    evaluator = _Evaluator(active)
    value = evaluator.eval(program["expression"], scope)
    _validate_json(value, active)
    canonical_bytes(value, limits=active)
    record = {
        "schema": RESULT_SCHEMA,
        "program_hash": program["content_hash"],
        "inputs_hash": content_address(scope, limits=active),
        "steps": evaluator.steps,
        "value": copy.deepcopy(value),
    }
    record["content_hash"] = content_address(record, limits=active)
    return record


__all__ = [
    "PROGRAM_SCHEMA",
    "RESULT_SCHEMA",
    "OPERATIONS",
    "FormalAssertionError",
    "FormalBudgetExceeded",
    "FormalError",
    "FormalEvaluationError",
    "FormalValidationError",
    "Limits",
    "attach_program_hash",
    "canonical_bytes",
    "content_address",
    "evaluate",
    "evaluate_with_steps",
    "make_program",
    "program_content_hash",
    "rational",
    "run_program",
    "verify_program_hash",
]
