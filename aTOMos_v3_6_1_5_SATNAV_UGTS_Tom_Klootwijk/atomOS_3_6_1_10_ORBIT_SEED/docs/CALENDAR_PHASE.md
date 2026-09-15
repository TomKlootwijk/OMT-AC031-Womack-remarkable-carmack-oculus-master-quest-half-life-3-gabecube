# Gregorian calendar and phase verification

A single January-to-December sequence does not cover the Gregorian leap rules.
The calendar continues into the next year; it does not flip back when a month,
year or key phase ends. Release 3.6.1.10 now checks the complete 400-year Gregorian
cycle, **2000-01-01 through 2399-12-31**, and the following 2400-01-01 boundary.
This is calendar/address verification, not a 400-year satellite forecast.

The executable audit is [validate_calendar_phase.py](../tools/validate_calendar_phase.py).
Its [recorded result](../results/calendar_phase_36110/summary.json) passes
**9,519,315 exact comparisons with zero failures**. Seven focused regression
tests also pass; deliberately broken calendar-reset and lost-winding substitutes
are detected. No runtime equations, force coefficients or packed seed bytes changed.
The report records the actual runtime/tool/test source hashes and all eight seed
file hashes.

| Coverage | Verified count |
|---|---:|
| Dates in the 400-year cycle | 146,097 |
| Daily midnights, including 2400-01-01 | 146,098 |
| Month starts / year starts | 4,800 / 400 |
| Leap days in the cycle | 97 |
| GPST formatter checks over daily dates | 438,293 |
| Additional formatter checks at explicit century/epoch boundaries | 22 |
| 14-bit phase wraps within the calendar interval | 770,433 |
| Ticks immediately before, at and after those wraps | 2,311,299 |
| All 16,384 phase indices at three signed winding offsets | 49,152 |
| Large signed tick/reference cases | 210 |
| Complete daily chart records, including both key layouts | 146,098 |

The century cases explicitly include 1900, 2100, 2200 and 2300 as common years,
and 2000 and 2400 as leap years. The 2400-02-29 cases are separate boundary
tests outside the enumerated cycle. The formatter is also checked at GPS epoch
and the preceding second. Daily checks include midnight, an exactly representable
0.125-second fraction and the previous date's 23:59:59, so both formatting and
day-to-day carry are exercised.

## Independent calendar arithmetic

Expected dates come from explicit year/month/day enumeration, without using
`datetime` as the expected-value oracle. For year `Y`, month `M` and day `D`, the
March-based integer oracle uses

```text
a = (14 - M) // 12
y = Y + 4800 - a
m = M + 12*a - 3
J = D + (153*m + 2)//5 + 365*y + y//4 - y//100 + y//400 - 32045
T = (J - J(1980, 1, 6)) * 86400
```

`J` is the astronomical-noon Julian day number associated with the calendar date;
only integer date differences are used to construct midnight ticks. A separate
January-based ordinal sum is checked for every date, and each date must advance
the JDN by exactly one. Known epoch/JDN anchors are regression-tested.

The Gregorian leap predicate is
`Y % 4 == 0 and (Y % 100 != 0 or Y % 400 == 0)`.
In this cycle it gives `100 - 4 + 1 = 97` leap days and
`400*365 + 97 = 146097 = 7*20871` days. The month/leap pattern and weekdays repeat
after 400 years, while the year number and absolute timestamp continue. For every
enumerated date, the JDN difference to the same date 400 years later is checked
as 146,097 with zero weekday remainder; this last comparison is arithmetic, not
another 400 years of formatter or orbit testing.

## Exact phase carry and the two keys

For integer tick `T`, reference `T0` and `P = 2**14 = 16384`, the runtime uses

```text
w, r = divmod(T - T0, P)
T = T0 + P*w + r,   0 <= r < P
phase_fraction = r / P
```

The independent test oracle uses arithmetic right shift and a 14-bit mask.
It tests every phase value at zero, negative and positive offsets, and separate
signed tick/reference cases reaching `10**100 + 16385`. The fractional value is
exact in binary64 because its denominator is a power of two and its numerator
has at most 14 bits. The large-integer claim applies to the integer helper;
`timestamp_gpst` and the chart's binary64 time input do not represent arbitrary-size
integer seconds exactly.

Both the original contiguous and Morton codecs are checked against independently
constructed bit strings and decoded back to all four indices. Their time field
stores only `r`: ticks separated by `P` can produce the same key. Explicit collision
tests require the winding to increase by one. Daily chart checks retain the
absolute tick and winding separately, so that key repetition cannot silently
reset calendar time. At the tested one-second tick period, a phase repeats every
16,384 seconds; it is not a calendar month or year.

## Scope and reproduction

`timestamp_gpst` formats uniform 86,400-second days and explicitly labels its
output **GPST**. These checks do not validate UTC leap-second conversion, predict
future UTC offsets, or certify sub-millisecond formatter accuracy. They do not
expand any physical model's timestamp domain or its measured forecast horizon.
The orbit model still enforces its stored domain and retains its existing sampled
accuracy evidence.

```powershell
python tools/validate_calendar_phase.py
python -m unittest discover -s tests -p test_calendar_phase.py -v
```
