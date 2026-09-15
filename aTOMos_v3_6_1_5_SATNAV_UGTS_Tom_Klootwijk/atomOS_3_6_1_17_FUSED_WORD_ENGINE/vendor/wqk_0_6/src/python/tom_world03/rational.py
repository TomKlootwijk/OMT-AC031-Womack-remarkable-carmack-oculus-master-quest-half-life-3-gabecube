"""Exact canonical rational numbers used by interval-event certificates."""
from __future__ import annotations

from dataclasses import dataclass
from fractions import Fraction
from math import gcd
from typing import Any


@dataclass(frozen=True, slots=True)
class Q:
    numerator: int
    denominator: int = 1

    def __post_init__(self) -> None:
        n = int(self.numerator)
        d = int(self.denominator)
        if d == 0:
            raise ValueError("rational denominator must be nonzero")
        if d < 0:
            n, d = -n, -d
        g = gcd(abs(n), d)
        object.__setattr__(self, "numerator", n // g)
        object.__setattr__(self, "denominator", d // g)

    @classmethod
    def from_value(cls, value: Any) -> "Q":
        if isinstance(value, cls):
            return value
        if isinstance(value, Fraction):
            return cls(value.numerator, value.denominator)
        if isinstance(value, bool):
            return cls(int(value), 1)
        if isinstance(value, int):
            return cls(value, 1)
        if isinstance(value, str):
            text = value.strip()
            if "/" in text:
                left, right = text.split("/", 1)
                return cls(int(left, 0), int(right, 0))
            return cls(int(text, 0), 1)
        if isinstance(value, dict):
            if set(value) >= {"num", "den"}:
                return cls(int(value["num"]), int(value["den"]))
            if set(value) >= {"numerator", "denominator"}:
                return cls(int(value["numerator"]), int(value["denominator"]))
        raise TypeError(f"cannot convert {type(value).__name__} to Q")

    def as_fraction(self) -> Fraction:
        return Fraction(self.numerator, self.denominator)

    def to_record(self) -> dict[str, int]:
        return {"num": self.numerator, "den": self.denominator}

    def to_text(self) -> str:
        if self.denominator == 1:
            return str(self.numerator)
        return f"{self.numerator}/{self.denominator}"

    def sign(self) -> int:
        return (self.numerator > 0) - (self.numerator < 0)

    def is_integer(self) -> bool:
        return self.denominator == 1

    def as_integer(self) -> int:
        if self.denominator != 1:
            raise ValueError(f"{self.to_text()} is not an integer")
        return self.numerator

    def floor(self) -> int:
        return self.numerator // self.denominator

    def ceil(self) -> int:
        return -((-self.numerator) // self.denominator)

    def __neg__(self) -> "Q":
        return Q(-self.numerator, self.denominator)

    def __abs__(self) -> "Q":
        return Q(abs(self.numerator), self.denominator)

    def __add__(self, other: Any) -> "Q":
        b = Q.from_value(other)
        return Q(self.numerator * b.denominator + b.numerator * self.denominator,
                 self.denominator * b.denominator)

    def __radd__(self, other: Any) -> "Q":
        return self + other

    def __sub__(self, other: Any) -> "Q":
        return self + (-Q.from_value(other))

    def __rsub__(self, other: Any) -> "Q":
        return Q.from_value(other) - self

    def __mul__(self, other: Any) -> "Q":
        b = Q.from_value(other)
        return Q(self.numerator * b.numerator, self.denominator * b.denominator)

    def __rmul__(self, other: Any) -> "Q":
        return self * other

    def __truediv__(self, other: Any) -> "Q":
        b = Q.from_value(other)
        if b.numerator == 0:
            raise ZeroDivisionError("rational division by zero")
        return Q(self.numerator * b.denominator, self.denominator * b.numerator)

    def __rtruediv__(self, other: Any) -> "Q":
        return Q.from_value(other) / self

    def __lt__(self, other: Any) -> bool:
        b = Q.from_value(other)
        return self.numerator * b.denominator < b.numerator * self.denominator

    def __le__(self, other: Any) -> bool:
        return self == Q.from_value(other) or self < other

    def __gt__(self, other: Any) -> bool:
        return not self <= other

    def __ge__(self, other: Any) -> bool:
        return not self < other

    def __int__(self) -> int:
        return self.as_integer()

    def __str__(self) -> str:
        return self.to_text()
