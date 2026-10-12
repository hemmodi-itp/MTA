"""Phase 3.2 — boundary value analysis: exact expected values and properties (hypothesis)."""

import datetime as dt
from decimal import Decimal

from hypothesis import given, settings, strategies as st

from tools.test_design.bva import date_points, fmt_number, length_points, numeric_points, size_points

D = Decimal


def _vals(points):
    return [(label, v, ok) for label, v, ok in points]


# ── exact values ──────────────────────────────────────────────────────────────

def test_integer_range_1_to_99():
    assert _vals(numeric_points(D(1), D(99), D(1))) == [
        ("min-1", D(0), False), ("min", D(1), True), ("min+1", D(2), True), ("nominal", D(50), True),
        ("max-1", D(98), True), ("max", D(99), True), ("max+1", D(100), False)]


def test_decimal_min_only_price():
    pts = numeric_points(D(0), None, D("0.01"))
    assert [(l, fmt_number(v, D("0.01")), ok) for l, v, ok in pts] == [
        ("min-1", "-0.01", False), ("min", "0.00", True), ("min+1", "0.01", True), ("nominal", "0.10", True)]


def test_exclusive_minimum_makes_min_itself_invalid():
    pts = numeric_points(D(0), D(10), D(1), lo_exclusive=True)
    assert pts[0] == ("min", D(0), False) and pts[1] == ("min+1", D(1), True)
    assert ("max+1", D(11), False) in pts


def test_length_1_to_50_name():
    assert _vals(length_points(1, 50)) == [
        ("min-1", 0, False), ("min", 1, True), ("min+1", 2, True), ("nominal", 26, True),
        ("max-1", 49, True), ("max", 50, True), ("max+1", 51, False)]


def test_length_max_only_and_negative_lengths_dropped():
    assert _vals(length_points(None, 500)) == [("nominal", 490, True), ("max-1", 499, True),
                                               ("max", 500, True), ("max+1", 501, False)]
    assert all(v >= 0 for _, v, _ in length_points(0, 3))


def test_tiny_range_dedupes_points():
    assert _vals(numeric_points(D(1), D(2), D(1))) == [
        ("min-1", D(0), False), ("min", D(1), True), ("min+1", D(2), True), ("max+1", D(3), False)]


def test_size_max_1mb():
    assert _vals(size_points(None, 1048576)) == [("max-1", 1048575, True), ("max", 1048576, True),
                                                 ("max+1", 1048577, False)]


def test_dates_leap_year_feb_29():
    # 3-day range: min+1, nominal and max-1 are all Feb 29 (leap year), kept once under the first label
    assert date_points(dt.date(2024, 2, 28), dt.date(2024, 3, 1)) == [
        ("min-1", dt.date(2024, 2, 27), False), ("min", dt.date(2024, 2, 28), True),
        ("min+1", dt.date(2024, 2, 29), True), ("max", dt.date(2024, 3, 1), True),
        ("max+1", dt.date(2024, 3, 2), False)]


def test_dates_non_leap_year_and_month_ends():
    pts = dict((l, v) for l, v, _ in date_points(dt.date(2023, 2, 28), dt.date(2023, 4, 30)))
    assert pts["min+1"] == dt.date(2023, 3, 1)           # 2023 is not a leap year
    assert pts["max+1"] == dt.date(2023, 5, 1)           # April has 30 days
    assert pts["max-1"] == dt.date(2023, 4, 29)
    year_end = dict((l, v) for l, v, _ in date_points(dt.date(2023, 1, 1), dt.date(2023, 12, 31)))
    assert year_end["min-1"] == dt.date(2022, 12, 31) and year_end["max+1"] == dt.date(2024, 1, 1)
    century = dict((l, v) for l, v, _ in date_points(dt.date(1900, 2, 28), None))
    assert century["min+1"] == dt.date(1900, 3, 1)       # 1900 is not a leap year (divisible by 100)
    y2000 = dict((l, v) for l, v, _ in date_points(dt.date(2000, 2, 28), None))
    assert y2000["min+1"] == dt.date(2000, 2, 29)        # 2000 is (divisible by 400)


def test_inverted_range_yields_nothing():
    assert numeric_points(D(10), D(1), D(1)) == []
    assert date_points(dt.date(2024, 5, 1), dt.date(2024, 4, 1)) == []


# ── properties ────────────────────────────────────────────────────────────────

@settings(max_examples=150, deadline=None)
@given(lo=st.integers(-1000, 1000), span=st.integers(0, 1000), step=st.sampled_from(["1", "0.5", "0.01"]))
def test_numeric_points_validity_matches_range(lo, span, step):
    s = D(step)
    a, b = D(lo), D(lo) + D(span) * s
    pts = numeric_points(a, b, s)
    assert pts == numeric_points(a, b, s)                                 # deterministic
    values = [v for _, v, _ in pts]
    assert len(values) == len(set(values))                                # no duplicates
    for _, v, ok in pts:
        assert ok == (a <= v <= b)                                        # valid ⇔ inside the range
    assert (a - s) in values and (b + s) in values                        # both just-outside points present
    assert a in values and b in values


@settings(max_examples=100, deadline=None)
@given(day=st.dates(min_value=dt.date(1900, 1, 2), max_value=dt.date(2099, 12, 30)), span=st.integers(0, 800))
def test_date_points_are_one_day_apart_at_the_edges(day, span):
    hi = day + dt.timedelta(days=span)
    if hi > dt.date(2099, 12, 30):
        return
    pts = dict((l, (v, ok)) for l, v, ok in date_points(day, hi))
    assert pts["min-1"] == (day - dt.timedelta(days=1), False)
    assert pts["max+1"] == (hi + dt.timedelta(days=1), False)
    assert all(ok == (day <= v <= hi) for v, ok in pts.values())
