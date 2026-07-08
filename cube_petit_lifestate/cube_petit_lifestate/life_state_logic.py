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
"""Pure life-state integration logic (ROS非依存).

LifeStateNode から切り出した自然変化の積分とクランプのロジック。
"""

from typing import Tuple


def clamp(value: float, low: float = 0.0, high: float = 1.0) -> float:
    """Value を [low, high] に収める."""
    return min(max(value, low), high)


def natural_step(
    attention: float,
    arousal: float,
    stress: float,
    loneliness: float,
    att_down: float,
    aro_down: float,
    str_down: float,
    lon_up: float,
    dt: float,
) -> Tuple[float, float, float, float]:
    """1タイマー刻みの自然変化を積分し、[0, 1] にクランプした状態を返す."""
    # ---- natural change ----
    attention -= 0.01 * att_down * dt
    arousal -= 0.005 * aro_down * dt
    loneliness += 0.02 * lon_up * dt
    stress -= 0.01 * str_down * dt

    return (
        clamp(attention),
        clamp(arousal),
        clamp(stress),
        clamp(loneliness),
    )
