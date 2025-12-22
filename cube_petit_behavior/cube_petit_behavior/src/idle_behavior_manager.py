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

import random
import time
from typing import Any, Dict, Optional


class IdleBehaviorManager:
    """Manager for selecting idle behaviors based on life state.

    Behavior changes are rate-limited by a hold time to avoid rapid switching.
    """

    def __init__(self, config: Dict[str, Any]) -> None:
        idle_cfg = config.get('idle_behavior', {})

        self.hold_time: float = float(idle_cfg.get('hold_time', 10.0))
        self.weights: Dict[str, float] = idle_cfg.get('weights', {})

        self.patrol_points = idle_cfg.get('patrol_points', [])
        self.favorite_pose = idle_cfg.get('favorite_pose', None)

        self.current_behavior: Optional[str] = None
        self.last_change_time: float = time.time()

    def update(self, life_state: str, now: float) -> None:
        """Update idle behavior based on life state."""
        if self.current_behavior is not None:
            if now - self.last_change_time < self.hold_time:
                return

        scores: Dict[str, float] = {
            'wander': life_state.loneliness * 0.5 + random.random() * 0.2,
            'patrol': life_state.arousal * 0.3,
            'favorite': life_state.loneliness * 0.8,
            'pause': 1.0 - life_state.arousal,
        }

        self.current_behavior = max(scores, key=scores.get)
        self.last_change_time = now

    def get_current_behavior(self) -> Optional[str]:
        """Return the currently selected idle behavior."""
        return self.current_behavior
