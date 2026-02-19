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
#



from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import EnvironmentVariable, LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare
from launch.substitutions import PathJoinSubstitution


def generate_launch_description() -> LaunchDescription:

    pkg_share = FindPackageShare('cube_petit_chat')

    model_arg = DeclareLaunchArgument(
        'model',
        default_value='gpt-4o'
    )

    api_key_arg = DeclareLaunchArgument(
        'api_key',
        default_value=EnvironmentVariable('OPENAI_API_KEY')
    )

    setting_file_arg = DeclareLaunchArgument(
        'setting_file',
        default_value=PathJoinSubstitution(
            [pkg_share, 'config', 'gpt_chat_setting.txt']
        ),
        description='GPT setting file'
    )

    gpt_node = Node(
        package='cube_petit_chat',
        executable='gpt_api_chat',
        name='gpt_chat',
        output='screen',
        parameters=[
            {
                'model': LaunchConfiguration('model'),
                'api_key': LaunchConfiguration('api_key'),
                'setting_file': LaunchConfiguration('setting_file'),
            }
        ]
    )

    return LaunchDescription([
        model_arg,
        api_key_arg,
        setting_file_arg,
        gpt_node
    ])
