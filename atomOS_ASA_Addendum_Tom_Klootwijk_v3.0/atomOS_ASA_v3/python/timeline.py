"""Rational frame bookkeeping for the source's 250 Hz / 128 Hz example."""
from __future__ import annotations
import math

def schedule(frame_rate: int=250, tick_rate: int=128) -> dict:
    if type(frame_rate) is not int or type(tick_rate) is not int or not 0 < frame_rate <= 1000000 or not 0 < tick_rate <= 1000000:
        raise ValueError('rates must be positive integers <= 1000000')
    base = math.lcm(frame_rate, tick_rate)
    g = math.gcd(frame_rate,tick_rate)
    return {'base_hz':base,'frame_ticks':base//frame_rate,'engine_ticks':base//tick_rate,
            'period_numerator':1,'period_denominator':g,'frames_per_period':frame_rate//g,'steps_per_period':tick_rate//g}

def latest_frame(k: int, frame_rate: int=250, tick_rate: int=128) -> int:
    schedule(frame_rate,tick_rate)
    if type(k) is not int or k<0:
        raise ValueError('engine tick must be a nonnegative integer')
    return k*frame_rate//tick_rate
