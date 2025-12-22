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

import os

from ament_index_python.packages import get_package_share_directory
from launch import LaunchDescription
from launch_ros.actions import Node


def generate_launch_description() -> LaunchDescription:
    """Generate launch description for Cube petit motion adapter."""
    pkg_share = get_package_share_directory('cube_petit_behavior')
    idle_yaml = os.path.join(pkg_share, 'config', 'idle_behavior.yaml')

    return LaunchDescription([
        Node(
            package='cube_petit_behavior',
            executable='motion_adapter',
            name='cube_petit_motion_adapter_node',
            parameters=[idle_yaml],
        ),
    ])
