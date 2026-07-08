#!/usr/bin/env python

# Copyright (c) 2025 SoftBank Corp.
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
#

"""Pure behavior-selection logic (ROS非依存).

BehaviorNode から切り出したヒステリシス選択とノイズ付加のロジック。
"""

import random
from typing import Dict, Optional


def add_random_noise(
    scores: Dict[str, float],
    magnitude: float = 0.05,
    rng: Optional[random.Random] = None,
) -> None:
    """Add small random noise to each score."""
    uniform = rng.uniform if rng is not None else random.uniform
    for key in scores:
        scores[key] += uniform(-magnitude, magnitude)


def select_with_hysteresis(
    scores: Dict[str, float],
    last: Optional[str],
    now: float,
    last_change_time: float,
    hysteresis: float,
    hold_time: float,
) -> str:
    """Select the best intent with hysteresis and hold-time constraints."""
    best = max(scores, key=scores.get)

    if last is None:
        return best

    if best != last:
        diff = scores[best] - scores[last]

        if diff < hysteresis:
            return last

        if now - last_change_time < hold_time:
            return last

    return best
