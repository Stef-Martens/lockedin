from datetime import date, timedelta

import pytest

from lockedin.forecast.trend import crossing, deadline, fit, month_part, project

TODAY = date(2026, 10, 27)


def weekly(start: float, per_week: float, weeks: int = 12, noise=(0.0,)) -> list[tuple[date, float]]:
    return [(TODAY - timedelta(weeks=weeks - 1 - i), start + per_week * i + noise[i % len(noise)]) for i in range(weeks)]


def test_a_steady_rise_is_projected_with_a_widening_band():
    t = fit(weekly(80, 0.5, noise=(0.4, -0.3, 0.1)), TODAY)
    assert t.per_week == pytest.approx(0.5, abs=0.1)
    proj = project(t, weeks=20, flatten=False)
    assert proj[0][0] == TODAY + timedelta(weeks=1)
    widths = [hi - lo for _, _, lo, hi in proj]
    assert widths == sorted(widths) and all(lo <= mid <= hi for _, mid, lo, hi in proj)
    assert proj[-1][1] == pytest.approx(85.5 + 0.5 * 20, abs=1.5)


def test_gains_flatten_for_strength():
    t = fit(weekly(80, 1.0), TODAY)
    straight, flattened = project(t, 52, flatten=False), project(t, 52, flatten=True)
    assert flattened[-1][1] < straight[-1][1] - 10 and flattened[-1][1] > flattened[0][1]


def test_too_little_data_is_no_trend():
    assert fit(weekly(80, 0.5, weeks=3), TODAY) is None
    assert fit([(TODAY - timedelta(days=d), 80.0) for d in (0, 7, 14, 21)], TODAY) is None  # 3 weeks: too short
    assert fit([(TODAY - timedelta(days=d), 80.0) for d in (0, 7, 14, 28)], TODAY) is not None


def test_crossing_dates_likely_between_early_and_late():
    t = fit(weekly(80, 0.5, noise=(0.8, -0.8)), TODAY)
    likely, early, late = crossing(project(t, 52, flatten=False), 90, lower_is_better=False)
    assert early <= likely <= late
    assert crossing(project(fit(weekly(80, 0.0), TODAY), 52, flatten=False), 90, False)[0] is None


def test_lower_is_better_crosses_downwards():
    t = fit(weekly(27.0, -0.1), TODAY)  # a 5k time in minutes, getting faster
    likely, _, _ = crossing(project(t, 52, flatten=False), 25.0, lower_is_better=True)
    assert likely is not None and likely > TODAY


@pytest.mark.parametrize("words, expected", [
    ("Bench 100 kg by March 2027", date(2027, 3, 31)),
    ("Run a 10K by june", date(2027, 6, 30)),
    ("Squat 140 kg by end of December", date(2026, 12, 31)),
    ("Swim 1500 m before 15 January 2027", date(2027, 1, 15)),
    ("FTP 200 W by 2027-04-01", date(2027, 4, 1)),
    ("Lose weight in 12 weeks", date(2026, 10, 1) + timedelta(weeks=12)),
    ("Bench 100 kg", None),
    ("Run 5k in 25 min", None),
])
def test_deadline_from_the_goals_words(words, expected):
    assert deadline(words, created=date(2026, 10, 1), today=TODAY) == expected


@pytest.mark.parametrize("d, expected", [
    (date(2027, 3, 4), "early March 2027"), (date(2026, 11, 15), "mid-November"), (date(2026, 12, 28), "late December"),
])
def test_month_part(d, expected):
    assert month_part(d, TODAY) == expected
