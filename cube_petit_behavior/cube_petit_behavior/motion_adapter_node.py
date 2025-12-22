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
from typing import Optional

import rclpy
from rclpy.node import Node
from std_msgs.msg import String

from cube_petit_behavior.src.idle_behavior_manager import IdleBehaviorManager
from cube_petit_interaction_msgs.msg import LifeState


class MotionAdapter(Node):
    """Adapter node that converts motion intents into concrete behaviors.

    Idle intent is delegated to IdleBehaviorManager, while non-idle intents
    are forwarded directly (currently for debug purposes).
    """

    def __init__(self) -> None:
        super().__init__('cube_petit_motion_adapter')

        if self.has_parameter('idle_behavior'):
            idle_behavior_param = self.get_parameter('idle_behavior').value
        else:
            idle_behavior_param = {}

        self.idle_manager = IdleBehaviorManager({'idle_behavior': idle_behavior_param})

        self.sub_intent = self.create_subscription(
            String,
            'behavior/motion_intent',
            self.on_motion_intent,
            10,
        )

        self.sub_life = self.create_subscription(
            LifeState,
            'internal/life_state',
            self.on_life_state,
            10,
        )

        self.debug_pub = self.create_publisher(
            String,
            'motion/debug',
            10,
        )

        self.current_intent: Optional[str] = None
        self.life_state: Optional[LifeState] = None

        self.timer = self.create_timer(0.2, self.on_timer)

        self.get_logger().info('Motion adapter started')

    # ================= callbacks =================

    def on_motion_intent(self, msg: String) -> None:
        """Receive motion intent."""
        self.current_intent = msg.data

    def on_life_state(self, msg: LifeState) -> None:
        """Receive latest life state."""
        self.life_state = msg

    def on_timer(self) -> None:
        """Periodic update loop."""
        if self.current_intent is None or self.life_state is None:
            return

        now = time.time()

        if self.current_intent == 'idle':
            self.idle_manager.update(self.life_state, now)
            behavior = self.idle_manager.get_current_behavior()
            self.publish_debug(f'idle:{behavior}')
            return

        self.publish_debug(f'intent:{self.current_intent}')

    # ================= helper =================

    def publish_debug(self, text: str) -> None:
        """Publish debug text to motion/debug."""
        msg = String()
        msg.data = text
        self.debug_pub.publish(msg)
        self.get_logger().info(text)


def main() -> None:
    rclpy.init()
    node = MotionAdapter()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
