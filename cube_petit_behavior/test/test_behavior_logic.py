#!/usr/bin/env python

# Copyright (c) 2026 SoftBank Corp.
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.
# You may obtain a copy of the License at
#
#     http://www.apache.org/licenses/LICENSE-2.0
#
# Unless required by applicable law or agreed to in writing, software
# distributed under the License is distributed on an "AS IS" BASIS,
# WITHOUT WARRANTIES OR CONDITIONS OF ANY KIND, either express or implied.
# See the License for the specific language governing permissions and
# limitations under the License.
"""behavior_logic の単体テスト (ROS非依存)."""

import random

from cube_petit_behavior.behavior_logic import add_random_noise
from cube_petit_behavior.behavior_logic import select_with_hysteresis

HYSTERESIS = 0.15
HOLD_TIME = 1.5


class TestSelectWithHysteresis:

    def test_first_selection_returns_best(self) -> None:
        """Last が None のときは制約なしで最良候補を返す."""
        scores = {'idle': 0.1, 'approach': 0.9, 'retreat': 0.2}
        result = select_with_hysteresis(scores, None, 100.0, 0.0, HYSTERESIS, HOLD_TIME)
        assert result == 'approach'

    def test_same_best_keeps_selection(self) -> None:
        """Best == last なら制約チェックなしでそのまま返す."""
        scores = {'idle': 0.1, 'approach': 0.9}
        result = select_with_hysteresis(scores, 'approach', 100.0, 99.9, HYSTERESIS, HOLD_TIME)
        assert result == 'approach'

    def test_stays_on_last_when_diff_below_hysteresis(self) -> None:
        """差がヒステリシス閾値未満なら現在の選択を維持する."""
        scores = {'idle': 0.5, 'approach': 0.6}  # diff = 0.1 < 0.15
        result = select_with_hysteresis(scores, 'idle', 100.0, 0.0, HYSTERESIS, HOLD_TIME)
        assert result == 'idle'

    def test_switches_when_diff_equals_hysteresis(self) -> None:
        """差がちょうど閾値のとき (diff < hysteresis が偽) は切り替わる."""
        scores = {'idle': 0.5, 'approach': 0.65}  # diff = 0.15
        result = select_with_hysteresis(scores, 'idle', 100.0, 0.0, HYSTERESIS, HOLD_TIME)
        assert result == 'approach'

    def test_switches_when_diff_exceeds_hysteresis(self) -> None:
        """差が閾値を超え、ホールド時間も経過していれば切り替わる."""
        scores = {'idle': 0.3, 'approach': 0.9}
        result = select_with_hysteresis(scores, 'idle', 100.0, 0.0, HYSTERESIS, HOLD_TIME)
        assert result == 'approach'

    def test_hold_time_blocks_switch(self) -> None:
        """差が十分でも直近の切り替えからホールド時間内なら維持する."""
        scores = {'idle': 0.3, 'approach': 0.9}
        # 前回変更から 1.0 秒 < hold_time 1.5 秒
        result = select_with_hysteresis(scores, 'idle', 100.0, 99.0, HYSTERESIS, HOLD_TIME)
        assert result == 'idle'

    def test_hold_time_boundary_allows_switch(self) -> None:
        """経過時間がちょうど hold_time なら (now - t < hold が偽) 切り替わる."""
        scores = {'idle': 0.3, 'approach': 0.9}
        result = select_with_hysteresis(scores, 'idle', 100.0, 98.5, HYSTERESIS, HOLD_TIME)
        assert result == 'approach'

    def test_tie_breaking_prefers_first_key(self) -> None:
        """同点のときは dict の先頭側 (max の仕様) が選ばれる."""
        scores = {'idle': 0.5, 'approach': 0.5, 'retreat': 0.5}
        result = select_with_hysteresis(scores, None, 100.0, 0.0, HYSTERESIS, HOLD_TIME)
        assert result == 'idle'

    def test_tie_with_last_keeps_last(self) -> None:
        """Best と last が同点 (diff=0 < hysteresis) なら last を維持する."""
        scores = {'idle': 0.5, 'approach': 0.5}
        result = select_with_hysteresis(scores, 'approach', 100.0, 0.0, HYSTERESIS, HOLD_TIME)
        assert result == 'approach'

    def test_zero_hysteresis_zero_hold(self) -> None:
        """閾値・ホールドがゼロならわずかな差でも即切り替わる."""
        scores = {'idle': 0.5, 'approach': 0.500001}
        result = select_with_hysteresis(scores, 'idle', 100.0, 100.0, 0.0, 0.0)
        assert result == 'approach'


class TestAddRandomNoise:

    def test_noise_within_bounds(self) -> None:
        """ノイズは ±magnitude の範囲に収まる."""
        rng = random.Random(42)
        for _ in range(100):
            scores = {'a': 0.5, 'b': 0.0, 'c': 1.0}
            original = dict(scores)
            add_random_noise(scores, magnitude=0.05, rng=rng)
            for key in original:
                assert abs(scores[key] - original[key]) <= 0.05

    def test_all_keys_modified_in_place(self) -> None:
        """すべてのキーに対して in-place で加算され、キー集合は不変."""
        rng = random.Random(0)
        scores = {'idle': 0.1, 'approach': 0.2, 'retreat': 0.3, 'rest': 0.4}
        add_random_noise(scores, rng=rng)
        assert set(scores.keys()) == {'idle', 'approach', 'retreat', 'rest'}

    def test_deterministic_with_seeded_rng(self) -> None:
        """同じシードなら同じ結果になる."""
        scores1 = {'a': 0.5, 'b': 0.5}
        scores2 = {'a': 0.5, 'b': 0.5}
        add_random_noise(scores1, rng=random.Random(7))
        add_random_noise(scores2, rng=random.Random(7))
        assert scores1 == scores2

    def test_default_rng_within_bounds(self) -> None:
        """Rng 未指定 (random.uniform) でも範囲内に収まる."""
        scores = {'a': 0.0}
        add_random_noise(scores)
        assert -0.05 <= scores['a'] <= 0.05
