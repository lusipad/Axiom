from __future__ import annotations

import math
import random
import unittest
from fractions import Fraction

import numpy as np

from axiom.five_axis.f3_sampling import _certified_abs_bound


class CertifiedPowerBoundTests(unittest.TestCase):
    def test_lost_small_positive_terms_cannot_underestimate_the_peak(self):
        coefficients = [1.0] + [2.0**-54] * 6
        result = _certified_abs_bound(np.array(coefficients), 1.0)
        exact_peak = Fraction(1) + 6 * Fraction(1, 2**54)
        self.assertGreaterEqual(Fraction.from_float(result), exact_peak)

    def test_power_product_and_sum_rounding_are_enclosed(self):
        rng = random.Random(817)
        for _ in range(100):
            coefficients = [math.ldexp(rng.uniform(-1, 1), rng.randint(-100, 100)) for _ in range(8)]
            span = math.ldexp(rng.uniform(0.5, 1), rng.randint(-20, 20))
            exact = sum((abs(Fraction.from_float(c)) * Fraction.from_float(span)**i for i, c in enumerate(coefficients)), Fraction(0))
            result = _certified_abs_bound(np.array(coefficients), span)
            self.assertGreaterEqual(Fraction.from_float(result), exact)

    def test_subnormal_terms_and_overflow_cannot_create_a_false_finite_bound(self):
        result = _certified_abs_bound(np.array([0.0, 5e-324]), 0.5)
        self.assertGreaterEqual(Fraction.from_float(result), Fraction.from_float(5e-324) / 2)
        self.assertEqual(_certified_abs_bound(np.array([1e308, 1e308]), 2.0), math.inf)

    def test_invalid_interval_or_coefficients_are_rejected(self):
        for coefficients, span in (([1.0], -1.0), ([float("nan")], 1.0), ([1.0], float("inf"))):
            with self.assertRaises(ValueError):
                _certified_abs_bound(np.array(coefficients), span)
