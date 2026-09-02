"""Explicit opt-in test wrapper for the real-data smart-indicator BDD."""

from __future__ import annotations

import os
import unittest

from tests.live_smart_indicator_formula_bdd import LIVE_FLAG, run_live_smart_indicator_formula_bdd


@unittest.skipUnless(os.environ.get(LIVE_FLAG) == "1", "requires explicit LIVE_SMART_INDICATOR_BDD=1")
class LiveSmartIndicatorFormulaBddTest(unittest.TestCase):
    def test_h5_dav_formula_combinations_use_real_snapshots(self):
        report = run_live_smart_indicator_formula_bdd()
        failures = [item for item in report["scenarios"] if not item["passed"]]
        self.assertFalse(failures, failures)
