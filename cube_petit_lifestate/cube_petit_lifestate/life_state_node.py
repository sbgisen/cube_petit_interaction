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

import rclpy
from rclpy.node import Node

from cube_petit_interaction_msgs.msg import LifeState


class LifeStateNode(Node):

    def __init__(self) -> None:
        super().__init__('cube_petit_life_state_node')

        # --- declare parameters ---
        self.declare_parameter('attention', 0.3)
        self.declare_parameter('arousal', 0.5)
        self.declare_parameter('stress', 0.0)
        self.declare_parameter('loneliness', 0.2)

        self.declare_parameter('attention_up_ac', 1.0)
        self.declare_parameter('arousal_up_ac', 1.0)
        self.declare_parameter('stress_up_ac', 1.0)
        self.declare_parameter('loneliness_up_ac', 1.0)

        self.declare_parameter('attention_down_ac', 1.0)
        self.declare_parameter('arousal_down_ac', 1.0)
        self.declare_parameter('stress_down_ac', 1.0)
        self.declare_parameter('loneliness_down_ac', 1.0)

        # --- internal state ---
        self.attention = self.get_parameter('attention').value
        self.arousal = self.get_parameter('arousal').value
        self.stress = self.get_parameter('stress').value
        self.loneliness = self.get_parameter('loneliness').value

        # --- coefficients ---
        self.att_up = self.get_parameter('attention_up_ac').value
        self.aro_up = self.get_parameter('arousal_up_ac').value
        self.str_up = self.get_parameter('stress_up_ac').value
        self.lon_up = self.get_parameter('loneliness_up_ac').value

        self.att_down = self.get_parameter('attention_down_ac').value
        self.aro_down = self.get_parameter('arousal_down_ac').value
        self.str_down = self.get_parameter('stress_down_ac').value
        self.lon_down = self.get_parameter('loneliness_down_ac').value

        # --- publisher ---
        self.publisher_ = self.create_publisher(LifeState, 'internal/life_state', 10)

        # --- timer ---
        self.dt = 0.1  # 100ms
        self.timer = self.create_timer(self.dt, self.on_timer)

        self.get_logger().info('LifeState node started')

    def on_timer(self) -> None:
        # ---- natural change ----
        self.attention -= 0.01 * self.att_down * self.dt
        self.arousal -= 0.005 * self.aro_down * self.dt
        self.loneliness += 0.02 * self.lon_up * self.dt
        self.stress -= 0.01 * self.str_down * self.dt

        self.clamp()

        msg = LifeState()
        msg.attention = float(self.attention)
        msg.arousal = float(self.arousal)
        msg.stress = float(self.stress)
        msg.loneliness = float(self.loneliness)

        self.publisher_.publish(msg)

    def clamp(self) -> None:
        self.attention = min(max(self.attention, 0.0), 1.0)
        self.arousal = min(max(self.arousal, 0.0), 1.0)
        self.stress = min(max(self.stress, 0.0), 1.0)
        self.loneliness = min(max(self.loneliness, 0.0), 1.0)


def main() -> None:
    rclpy.init()
    node = LifeStateNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
