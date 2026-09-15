"""Calendar/address oracle checks; these do not expand an orbit seed's domain."""
import sys
from pathlib import Path
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "tools"))
import validate_calendar_phase as audit


class CalendarPhaseTests(unittest.TestCase):
    def test_independent_calendar_anchors(self):
        for date, day_number in (((1980, 1, 6), 2444245), ((2000, 1, 1), 2451545),
                                 ((2400, 1, 1), 2597642), ((1, 1, 1), 1721426)):
            self.assertEqual(audit.jdn(*date), day_number)
            self.assertEqual(audit.jdn(*date) - audit.ordinal(*date), 1721425)
        self.assertEqual(audit.midnight_tick((1980, 1, 6)), 0)

    def test_century_leap_rule_and_full_cycle_count(self):
        self.assertEqual([audit.leap_year(y) for y in (2000, 2100, 2200, 2300, 2400)],
                         [True, False, False, False, True])
        sequence = list(audit.dates(2000, 2400))
        self.assertEqual(len(sequence), 146097)
        self.assertEqual(sum(date[1:] == (2, 29) for date in sequence), 97)
        self.assertEqual(146097 % 7, 0)

    def test_runtime_century_rollover_against_arithmetic(self):
        checks = audit.Checks()
        result = audit.audit_calendar(checks, 2099, 2101)
        self.assertEqual(result["dates_in_cycle"], 730)
        self.assertEqual(checks.failure_count, 0, checks.failures)
        self.assertEqual(audit.timestamp_gpst(-1), "1980-01-05T23:59:59.000 GPST")

    def test_explicit_centuries_and_next_cycle_leap_day(self):
        checks = audit.Checks()
        result = audit.audit_extra_boundaries(checks)
        self.assertEqual(len(result["century_transitions"]), 10)
        self.assertEqual(checks.failure_count, 0, checks.failures)

    def test_oracle_detects_repeating_calendar_formatter(self):
        checks = audit.Checks()
        with patch.object(audit, "timestamp_gpst", return_value="2000-01-01T00:00:00.000 GPST"):
            audit.audit_calendar(checks, 2099, 2100)
        self.assertGreater(checks.failure_count, 1000)

    def test_exact_phase_large_signed_carry_and_both_keys(self):
        checks = audit.Checks()
        for tick in (-10 ** 100, -(1 << 63) - 1, -16385, -16384, -1, 0, 16383, 16384, 10 ** 100 + 1):
            audit.check_phase(checks, tick)
            audit.check_phase(checks, tick, -10 ** 80)
            first = audit.check_codecs(checks, tick)
            self.assertEqual(first, audit.check_codecs(checks, tick + audit.PERIOD))
            self.assertEqual(audit.phase_winding(tick + audit.PERIOD, 0, audit.PERIOD)[0],
                             audit.phase_winding(tick, 0, audit.PERIOD)[0] + 1)
        self.assertEqual(checks.failure_count, 0, checks.failures)

    def test_oracle_detects_lost_winding(self):
        checks = audit.Checks()
        with patch.object(audit, "phase_winding", return_value=(0, 0.)):
            audit.check_phase(checks, 16384)
        self.assertEqual(checks.failure_count, 2)


if __name__ == "__main__":
    unittest.main(verbosity=2)
