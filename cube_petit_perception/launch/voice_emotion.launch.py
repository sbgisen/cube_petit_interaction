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

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import GroupAction
from launch.substitutions import EnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.actions import PushRosNamespace


def generate_launch_description() -> LaunchDescription:
    """Generate launch descriptions.

    Returns:
        Launch descriptions
    """
    return LaunchDescription([
        DeclareLaunchArgument('robot', default_value='cube_petit_pink', description='Robot namespace.'),
        GroupAction([
            PushRosNamespace(LaunchConfiguration('robot')),
            Node(
                package='cube_petit_perception',
                executable='voice_emotion_node',
                name='voice_emotion_node',
                output='screen',
                parameters=[{
                    'api_key': EnvironmentVariable('EMPATH_API'),
                    'start_enable': True,
                }],
            )
        ])
    ])
