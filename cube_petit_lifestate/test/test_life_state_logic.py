#!/usr/bin/env python

# Copyright (c) 2026 SoftBank Corp.
#
# <<licensetext>>

"""life_state_logic の単体テスト (ROS非依存)."""

import pytest

from cube_petit_lifestate.life_state_logic import clamp
from cube_petit_lifestate.life_state_logic import natural_step

DT = 0.1  # LifeStateNode のタイマー周期


class TestClamp:

    def test_within_range(self):
        assert clamp(0.5) == 0.5

    def test_below_lower_bound(self):
        assert clamp(-0.3) == 0.0

    def test_above_upper_bound(self):
        assert clamp(1.7) == 1.0

    def test_exact_bounds(self):
        assert clamp(0.0) == 0.0
        assert clamp(1.0) == 1.0

    def test_custom_bounds(self):
        assert clamp(5.0, low=-1.0, high=2.0) == 2.0
        assert clamp(-5.0, low=-1.0, high=2.0) == -1.0


class TestNaturalStep:

    def test_single_step_values(self):
        """係数 1.0 のとき 1 ステップの変化量が仕様どおり."""
        att, aro, stress, lon = natural_step(
            0.5, 0.5, 0.5, 0.2,
            1.0, 1.0, 1.0, 1.0, DT)
        assert att == pytest.approx(0.5 - 0.01 * DT)     # attention は減衰
        assert aro == pytest.approx(0.5 - 0.005 * DT)    # arousal は減衰
        assert stress == pytest.approx(0.5 - 0.01 * DT)  # stress は減衰
        assert lon == pytest.approx(0.2 + 0.02 * DT)     # loneliness は増加

    def test_decay_directions(self):
        """attention/arousal/stress は減少方向、loneliness は増加方向."""
        att, aro, stress, lon = natural_step(
            0.5, 0.5, 0.5, 0.5,
            1.0, 1.0, 1.0, 1.0, DT)
        assert att < 0.5
        assert aro < 0.5
        assert stress < 0.5
        assert lon > 0.5

    def test_clamped_at_lower_bound(self):
        """0.0 の状態は負にならない."""
        att, aro, stress, lon = natural_step(
            0.0, 0.0, 0.0, 0.0,
            1.0, 1.0, 1.0, 1.0, DT)
        assert att == 0.0
        assert aro == 0.0
        assert stress == 0.0
        assert lon > 0.0  # loneliness だけは増える

    def test_clamped_at_upper_bound(self):
        """loneliness は 1.0 を超えない."""
        _, _, _, lon = natural_step(
            0.5, 0.5, 0.5, 1.0,
            1.0, 1.0, 1.0, 1.0, DT)
        assert lon == 1.0

    def test_coefficients_scale_change(self):
        """係数が変化量をスケールする."""
        att1, _, _, _ = natural_step(0.5, 0.5, 0.5, 0.5, 1.0, 1.0, 1.0, 1.0, DT)
        att2, _, _, _ = natural_step(0.5, 0.5, 0.5, 0.5, 2.0, 1.0, 1.0, 1.0, DT)
        assert (0.5 - att2) == pytest.approx(2.0 * (0.5 - att1))

    def test_zero_dt_no_change(self):
        """dt = 0 なら状態は変わらない."""
        state = natural_step(0.3, 0.5, 0.1, 0.2, 1.0, 1.0, 1.0, 1.0, 0.0)
        assert state == (0.3, 0.5, 0.1, 0.2)

    def test_repeated_steps_converge(self):
        """繰り返し積分すると attention→0、loneliness→1 に収束する."""
        att, aro, stress, lon = 0.5, 0.5, 0.5, 0.5
        for _ in range(10000):
            att, aro, stress, lon = natural_step(
                att, aro, stress, lon,
                1.0, 1.0, 1.0, 1.0, DT)
        assert att == 0.0
        assert stress == 0.0
        assert lon == 1.0

    def test_output_always_in_range(self):
        """出力は常に [0, 1] に収まる."""
        for state in natural_step(0.5, 0.5, 0.5, 0.5, 100.0, 100.0, 100.0, 100.0, 10.0):
            assert 0.0 <= state <= 1.0
