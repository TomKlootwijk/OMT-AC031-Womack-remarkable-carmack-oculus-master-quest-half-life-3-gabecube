#!/usr/bin/env python3
"""Hinge Fields — computational companion for Tom Klootwijk.

Python 3.10+, standard library only.
Run: python Hinge_Field_Companion_Tom_Klootwijk.py
Run tests only: python Hinge_Field_Companion_Tom_Klootwijk.py --test

Analytic benchmark geometry and mechanics, not measured animal parameters.
The bracket solver resolves a supplied sign-changing interval. It is not a
complete collision detector: grazing roots and multiple unbracketed events
require additional detection logic. SI units are used throughout.
"""
from __future__ import annotations
import argparse
from dataclasses import dataclass
import json
import math
from typing import Callable, Sequence
import unittest

Vec3 = tuple[float, float, float]
Mat3 = tuple[Vec3, Vec3, Vec3]


def v3(x: Sequence[float]) -> Vec3:
    if len(x) != 3 or not all(math.isfinite(float(a)) for a in x):
        raise ValueError("Expected three finite coordinates.")
    return (float(x[0]), float(x[1]), float(x[2]))


def dot(a: Vec3, b: Vec3) -> float:
    return sum(x * y for x, y in zip(a, b))


def sub(a: Vec3, b: Vec3) -> Vec3:
    return v3([x - y for x, y in zip(a, b)])


def norm(a: Vec3) -> float:
    return math.sqrt(dot(a, a))


def matvec(A: Mat3, x: Vec3) -> Vec3:
    return v3([dot(row, x) for row in A])


def transpose(A: Mat3) -> Mat3:
    return tuple(v3([A[j][i] for j in range(3)]) for i in range(3))  # type: ignore[return-value]


def rodrigues(axis: Vec3, angle: float) -> Mat3:
    axis = v3(axis)
    length = norm(axis)
    if length == 0 or not math.isfinite(angle):
        raise ValueError("Axis must be nonzero and angle must be finite.")
    e = v3([v / length for v in axis])
    x, y, z = e
    E: Mat3 = ((0.0, -z, y), (z, 0.0, -x), (-y, x, 0.0))
    c, s = math.cos(angle), math.sin(angle)
    return tuple(v3([c * (i == j) + (1-c)*e[i]*e[j] + s*E[i][j]
                    for j in range(3)]) for i in range(3))  # type: ignore[return-value]


def sd_sphere(p: Vec3, center: Vec3, radius: float) -> float:
    if not math.isfinite(radius) or radius <= 0:
        raise ValueError("Radius must be positive and finite.")
    return norm(sub(v3(p), v3(center))) - radius


def sphere_normal(p: Vec3, center: Vec3) -> Vec3:
    r = sub(v3(p), v3(center))
    d = norm(r)
    if d == 0:
        raise ValueError("No unique sphere-distance gradient at the center.")
    return v3([x / d for x in r])


def sd_box(p: Vec3, half_extents: Vec3) -> float:
    """Exact Euclidean SDF of a centered axis-aligned solid box."""
    p, b = v3(p), v3(half_extents)
    if min(b) <= 0:
        raise ValueError("Half-extents must be positive.")
    q = v3([abs(x) - h for x, h in zip(p, b)])
    return norm(v3([max(x, 0.0) for x in q])) + min(max(q), 0.0)


def rigid_sdf(p: Vec3, R: Mat3, translation: Vec3,
              local_sdf: Callable[[Vec3], float]) -> float:
    """Pull back an SDF through a proper orthogonal rotation and translation.

    R must be a rotation matrix, for example produced by rodrigues().
    No anisotropic scaling is performed by this function.
    """
    return local_sdf(matvec(transpose(R), sub(v3(p), v3(translation))))


def bisect_event(g: Callable[[float], float], lo: float, hi: float,
                 time_tol: float = 1e-12, max_iterations: int = 200) -> float:
    """Resolve a continuous guard root in a supplied sign-changing bracket.

    The bracket should isolate the desired event. Direction, reset validity,
    simultaneous contacts and grazing detection belong to the caller.
    """
    if not (math.isfinite(lo) and math.isfinite(hi) and hi > lo):
        raise ValueError("Expected finite lo < hi.")
    if not math.isfinite(time_tol) or time_tol <= 0 or max_iterations < 1:
        raise ValueError("Positive finite tolerance and iteration limit required.")
    a, b = g(lo), g(hi)
    if not (math.isfinite(a) and math.isfinite(b)):
        raise ValueError("Non-finite guard value.")
    if a == 0: return lo
    if b == 0: return hi
    if (a > 0) == (b > 0):
        raise ValueError("No sign-changing bracket; a grazing root may still exist.")
    for _ in range(max_iterations):
        mid = (lo + hi) / 2
        m = g(mid)
        if not math.isfinite(m):
            raise ValueError("Non-finite guard value.")
        if m == 0 or (hi-lo)/2 <= time_tol:
            return mid
        if (a > 0) == (m > 0):
            lo, a = mid, m
        else:
            hi = mid
    raise RuntimeError("Root tolerance not reached.")


@dataclass(frozen=True)
class PlanarHinge:
    length: float = 0.004
    plane_x: float = 0.003
    tip_radius: float = 0.0002
    phi0: float = 1.2
    closing_speed: float = 100.0

    def __post_init__(self) -> None:
        if not all(math.isfinite(v) for v in vars(self).values()):
            raise ValueError("All parameters must be finite.")
        if self.length <= 0 or self.tip_radius < 0 or self.closing_speed <= 0:
            raise ValueError("Invalid length, radius or closing speed.")
        ratio = (self.plane_x-self.tip_radius)/self.length
        if not -1 < ratio < 1:
            raise ValueError("This benchmark requires a reachable transverse contact.")
        if not math.acos(ratio) < self.phi0 < math.pi:
            raise ValueError("Initial angle must lie on the separated monotone branch.")

    def phi(self, t: float) -> float:
        return self.phi0 - self.closing_speed*t

    def gap(self, t: float) -> float:
        return self.plane_x-self.length*math.cos(self.phi(t))-self.tip_radius

    def gap_rate(self, t: float) -> float:
        return -self.length*self.closing_speed*math.sin(self.phi(t))

    def exact_contact_time(self) -> float:
        phi_star = math.acos((self.plane_x-self.tip_radius)/self.length)
        return (self.phi0-phi_star)/self.closing_speed


def schmitt(values: Sequence[float], low: float, high: float,
            initial: int = 0) -> list[int]:
    if not (math.isfinite(low) and math.isfinite(high) and low < high):
        raise ValueError("Expected finite low < high.")
    if initial not in (0, 1):
        raise ValueError("Initial state must be zero or one.")
    state, result = initial, []
    for value in values:
        if not math.isfinite(value):
            raise ValueError("Non-finite sample.")
        if state == 0 and value >= high: state = 1
        elif state == 1 and value <= low: state = 0
        result.append(state)
    return result


def mm(A: list[list[float]], B: list[list[float]]) -> list[list[float]]:
    return [[sum(A[i][k]*B[k][j] for k in range(2)) for j in range(2)]
            for i in range(2)]


def bounce_final(y: float, v: float, T: float, e: float, g: float = 9.81) -> tuple[float, float]:
    """Exact one-bounce trajectory, for a test whose T is after first impact."""
    ti = (v + math.sqrt(v*v + 2*g*y))/g
    vm = v-g*ti
    rem = T-ti
    if not (0 < ti < T and rem < -2*e*vm/g):
        raise ValueError("Test horizon must include exactly one bounce.")
    vp = -e*vm
    return vp*rem-0.5*g*rem*rem, vp-g*rem


def benchmark_results() -> dict[str, object]:
    h = PlanarHinge()
    ts = h.exact_contact_time()
    tb = bisect_event(h.gap, 0.0, h.phi0/h.closing_speed)
    phi = h.phi(ts)
    J = h.length*math.sin(phi)
    inertia, restitution = 2e-11, 0.4
    impulse = (1+restitution)*h.closing_speed*inertia/J
    R, rho, gamma = 1e-4, 1000.0, 0.072
    vals = [-0.20, 0.02, -0.03, 0.04, -0.02, 0.20, 0.01, -0.02, 0.03, -0.20]
    hard = [int(x >= 0) for x in vals]
    hyst = schmitt(vals, -0.1, 0.1)
    transitions = lambda x: sum(a != b for a, b in zip(x[:-1], x[1:]))
    return {
        "parameters_are": "synthetic analytic benchmarks in SI units",
        "hinge": {
            "contact_angle_rad": phi,
            "contact_time_s": ts,
            "bisected_time_s": tb,
            "absolute_root_error_s": abs(tb-ts),
            "initial_gap_m": h.gap(0),
            "normal_closing_speed_m_per_s": -h.gap_rate(ts),
            "gap_jacobian_m_per_rad": J,
            "timing_sd_s_for_20um_gap_sd": 20e-6/abs(h.gap_rate(ts)),
            "quasistatic_force_N_for_2uNm_torque": 2e-6/J,
            "normal_impulse_Ns_for_stated_inertia": impulse,
            "energy_before_J": 0.5*inertia*h.closing_speed**2,
            "energy_after_J": 0.5*inertia*(restitution*h.closing_speed)**2,
        },
        "moving_sphere_contact_time_s": 0.002/0.21,
        "free_drop_capillary_time_s": math.sqrt(rho*R**3/gamma),
        "free_drop_quadrupole_frequency_Hz": math.sqrt(8*gamma/(rho*R**3))/(2*math.pi),
        "horizontal_ejectum_flight_s": math.sqrt(2*0.2/9.81),
        "horizontal_ejectum_range_m": 2*math.sqrt(2*0.2/9.81),
        "hysteresis_benchmark": {
            "inputs": vals, "hard_states": hard, "schmitt_states": hyst,
            "hard_transitions": transitions(hard), "schmitt_transitions": transitions(hyst)
        }
    }


class BenchmarkTests(unittest.TestCase):
    def test_sphere_sign(self) -> None:
        for x, expected in [(0.0, -1.0), (1.0, 0.0), (2.0, 1.0)]:
            self.assertAlmostEqual(sd_sphere((x,0,0), (0,0,0), 1), expected)

    def test_box_corner(self) -> None:
        self.assertAlmostEqual(sd_box((2,2,0), (1,1,1)), math.sqrt(2))
        self.assertEqual(sd_box((0,0,0), (1,2,3)), -1)

    def test_rotation_axis(self) -> None:
        e = v3([1/math.sqrt(3)]*3)
        for a,b in zip(matvec(rodrigues(e, .7), e), e): self.assertAlmostEqual(a,b)

    def test_rotation_length(self) -> None:
        p = (2.0, -3.0, 1.0)
        self.assertAlmostEqual(norm(matvec(rodrigues((1,2,3), 1.3), p)), norm(p))

    def test_rigid_pullback(self) -> None:
        R = rodrigues((0,0,1), .8)
        t, p = (1.0,2.0,3.0), (4.0,5.0,6.0)
        self.assertAlmostEqual(rigid_sdf(p,R,t,lambda x: sd_sphere(x,(0,0,0),2)), sd_sphere(p,t,2))

    def test_hinge_root(self) -> None:
        h = PlanarHinge()
        tb = bisect_event(h.gap, 0, h.phi0/h.closing_speed)
        self.assertLess(abs(tb-h.exact_contact_time()), 1e-12)

    def test_hinge_rate(self) -> None:
        h = PlanarHinge(); t = h.exact_contact_time(); eps = 1e-8
        fd = (h.gap(t+eps)-h.gap(t-eps))/(2*eps)
        self.assertAlmostEqual(fd,h.gap_rate(t), places=8)

    def test_grazing_not_a_bracket(self) -> None:
        g = lambda t: math.hypot(.2*t,.01)-.01
        self.assertEqual(g(0),0)
        with self.assertRaises(ValueError): bisect_event(g,-.005,.005)

    def test_schmitt_memory(self) -> None:
        self.assertEqual(schmitt([0,.2,0,-.2,0],-.1,.1),[0,1,1,0,0])

    def test_center_has_no_unique_normal(self) -> None:
        with self.assertRaises(ValueError): sphere_normal((0,0,0),(0,0,0))

    def test_invalid_inputs(self) -> None:
        with self.assertRaises(ValueError): rodrigues((0,0,0),0)
        with self.assertRaises(ValueError): sd_sphere((0,0,0),(0,0,0),-1)
        with self.assertRaises(ValueError): PlanarHinge(closing_speed=0)

    def test_saltation_against_finite_difference(self) -> None:
        y,v,T,e,g = .2,-.5,.22,.6,9.81
        ti = (v+math.sqrt(v*v+2*g*y))/g; vm = v-g*ti
        Xi = [[-e,0],[-(1+e)*g/vm,-e]]
        Fpre = [[1,ti],[0,1]]; Fpost = [[1,T-ti],[0,1]]
        predicted = mm(mm(Fpost,Xi),Fpre)
        eps = 1e-7
        for j in range(2):
            up = bounce_final(y+(eps if j==0 else 0),v+(eps if j==1 else 0),T,e)
            dn = bounce_final(y-(eps if j==0 else 0),v-(eps if j==1 else 0),T,e)
            for i in range(2): self.assertAlmostEqual(predicted[i][j],(up[i]-dn[i])/(2*eps),places=6)


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--test", action="store_true", help="Run tests without printing benchmark JSON.")
    args = parser.parse_args()
    suite = unittest.defaultTestLoader.loadTestsFromTestCase(BenchmarkTests)
    result = unittest.TextTestRunner(verbosity=2).run(suite)
    if not result.wasSuccessful(): raise SystemExit(1)
    if not args.test: print(json.dumps(benchmark_results(),indent=2))


if __name__ == "__main__":
    main()
