import pytest

from lockedin.fit.metrics import best_avg_power, normalized_power, training_stress

T = list(range(3600))


def test_np_constant():
    assert normalized_power([200] * 3600, T) == pytest.approx(200, abs=0.5)


def test_np_two_blocks():
    # (0.5·100⁴ + 0.5·300⁴)^¼ ≈ 253
    assert normalized_power([100] * 1800 + [300] * 1800, T) == pytest.approx(253, abs=3)


def test_np_too_short():
    assert normalized_power([200] * 20, list(range(20))) is None


def test_np_no_power():
    assert normalized_power([None] * 3600, T) is None


def test_np_resamples_sparse_samples():
    # 1 sample every 2 s at constant 200 W is still NP 200 after forward-fill
    assert normalized_power([200] * 1800, list(range(0, 3600, 2))) == pytest.approx(200, abs=0.5)


def test_np_long_gap_counts_as_zero():
    # 10 min at 200 W, a 10 min dropout, 10 min at 200 W: gap is zeros, so NP < 200
    t = list(range(600)) + list(range(1200, 1800))
    assert normalized_power([200] * 1200, t) < 190


def test_tss():
    assert training_stress(3600, 200, 250) == pytest.approx((0.8, 64.0))


def test_best_20m():
    assert best_avg_power([150] * 1800 + [250] * 1800, T, 1200) == pytest.approx(250)


def test_best_20m_shorter_than_window():
    assert best_avg_power([250] * 600, list(range(600)), 1200) is None
