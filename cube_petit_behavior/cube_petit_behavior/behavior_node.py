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

import time
from typing import Dict, Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from cube_petit_behavior import behavior_logic
from cube_petit_interaction_msgs.msg import LifeState


class BehaviorNode(Node):
    """Behavior selection node for Cube petit.

    This node converts internal life state and conversation status
    into discrete motion and gaze intents using hysteresis and hold-time logic.
    """

    def __init__(self) -> None:
        """Init."""
        super().__init__('cube_petit_behavior_node')

        self.declare_parameter('hysteresis_threshold', 0.15)
        self.declare_parameter('intent_hold_time', 1.5)

        self.hysteresis: float = self.get_parameter('hysteresis_threshold').value
        self.hold_time: float = self.get_parameter('intent_hold_time').value

        self.sub_life = self.create_subscription(
            LifeState,
            'internal/life_state',
            self.on_life_state,
            10,
        )

        self.sub_conversation = self.create_subscription(
            String,
            'conversation/status',
            self.on_conversation_status,
            10,
        )

        self.motion_pub = self.create_publisher(
            String,
            'behavior/motion_intent',
            10,
        )
        self.gaze_pub = self.create_publisher(
            String,
            'behavior/gaze_intent',
            10,
        )

        self.last_motion: Optional[str] = None
        self.last_gaze: Optional[str] = None
        self.last_change_time: float = time.time()

        self.conversation_status: str = 'idle'

        self.get_logger().info('Behavior node started')

    # ================= callbacks =================

    def on_conversation_status(self, msg: String) -> None:
        """Update current conversation status."""
        self.conversation_status = msg.data

    def on_life_state(self, s: LifeState) -> None:
        """Compute and publish motion/gaze intents from life state."""
        now = time.time()

        motion_scores: Dict[str, float] = {
            'idle': s.loneliness,
            'approach': s.attention * (1.0 - s.stress),
            'retreat': s.stress,
            'rest': 1.0 - s.arousal,
        }

        gaze_scores: Dict[str, float] = {
            'forward': 0.2,
            'human': s.attention,
            'away': s.stress,
        }

        if self.conversation_status in ('listening', 'speaking'):
            motion_scores['approach'] = -1.0
            motion_scores['retreat'] = -1.0
            gaze_scores['human'] += 0.5

        self.add_random_noise(motion_scores)
        self.add_random_noise(gaze_scores)

        motion = self.select_with_hysteresis(
            motion_scores,
            self.last_motion,
            now,
        )
        gaze = self.select_with_hysteresis(
            gaze_scores,
            self.last_gaze,
            now,
        )

        self.publish_if_changed(motion, gaze, now)

    # ================= logic =================

    def add_random_noise(self, scores: Dict[str, float]) -> None:
        """Add small random noise to each score."""
        behavior_logic.add_random_noise(scores)

    def select_with_hysteresis(
        self,
        scores: Dict[str, float],
        last: Optional[str],
        now: float,
    ) -> str:
        """Select the best intent with hysteresis and hold-time constraints."""
        return behavior_logic.select_with_hysteresis(
            scores,
            last,
            now,
            self.last_change_time,
            self.hysteresis,
            self.hold_time,
        )

    def publish_if_changed(
        self,
        motion: str,
        gaze: str,
        now: float,
    ) -> None:
        """Publish intents only when they change."""
        if motion != self.last_motion:
            msg = String()
            msg.data = motion
            self.motion_pub.publish(msg)
            self.last_motion = motion
            self.last_change_time = now
            self.get_logger().info(f'Motion intent: {motion}')

        if gaze != self.last_gaze:
            msg = String()
            msg.data = gaze
            self.gaze_pub.publish(msg)
            self.last_gaze = gaze
            self.last_change_time = now
            self.get_logger().info(f'Gaze intent: {gaze}')


def main() -> None:
    rclpy.init()
    node = BehaviorNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
