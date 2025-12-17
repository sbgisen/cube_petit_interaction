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

import ast

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.actions import OpaqueFunction
from launch.launch_context import LaunchContext
from launch.substitutions import EnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.substitutions import FindPackageShare


def launch_setup(context: LaunchContext) -> list:
    """Configure Azure-related parameters if 'use_azure' is true."""
    parameters = {
        'model': LaunchConfiguration('model'),
        'api_key': LaunchConfiguration('api_key'),
        'setting_file': LaunchConfiguration('setting_file'),
        'use_past_context': LaunchConfiguration('use_past_context'),
        'past_context_file': LaunchConfiguration('past_context_file'),
        'max_context_limit': LaunchConfiguration('max_context_limit'),
        'max_tokens': LaunchConfiguration('max_tokens'),
        'use_speech_action': LaunchConfiguration('use_speech_action'),
        'use_input_topic': LaunchConfiguration('use_input_topic'),
        'use_history': LaunchConfiguration('use_history'),
        'history_file': LaunchConfiguration('history_file'),
        'tool_names': LaunchConfiguration('tool_names'),
        'use_tools': LaunchConfiguration('use_tools'),
        'start_enable': LaunchConfiguration('start_enable'),
    }
    tool_names_str = LaunchConfiguration('tool_names').perform(context)
    try:
        tool_names = ast.literal_eval(tool_names_str)
        if not isinstance(tool_names, list):
            tool_names = [str(tool_names)]
    except Exception:
        tool_names = [n.strip() for n in tool_names_str.split(',') if n.strip()]
    for tool_name in tool_names:
        if not tool_name:
            continue
        pkg_arg_name = f'tools.{tool_name}.package'
        try:
            pkg_name = LaunchConfiguration(pkg_arg_name).perform(context)
            if not pkg_name:
                pkg_name = 'cube_petit_chat'
        except Exception:
            pkg_name = 'cube_petit_chat'
        pkg_share_path = FindPackageShare(pkg_name).perform(context)
        py_path = str(
            PathJoinSubstitution([pkg_share_path, 'config', 'tools', tool_name, f'{tool_name}.py']).perform(context))
        yaml_path = str(
            PathJoinSubstitution([pkg_share_path, 'config', 'tools', tool_name, f'{tool_name}.yaml']).perform(context))
        parameters[f'tools.{tool_name}.python_path'] = py_path
        parameters[f'tools.{tool_name}.yaml_path'] = yaml_path
        parameters[f'tools.{tool_name}.package'] = pkg_name

    return [
        Node(
            package='cube_petit_chat',
            executable='realtime_gpt_chat',
            name='realtime_gpt_chat',
            output='screen',
            parameters=[parameters],
        )
    ]


def generate_launch_description() -> LaunchDescription:
    """Generate launch descriptions.

    Returns:
        Launch descriptions
    """
    args = []
    pkg_path = FindPackageShare('cube_petit_chat')
    # arg list
    args.append(DeclareLaunchArgument('model', default_value='=gpt-4o-realtime-preview-2024-12-17'))
    args.append(DeclareLaunchArgument('api_key', default_value=EnvironmentVariable('OPENAI_API_KEY')))
    args.append(
        DeclareLaunchArgument('use_past_context',
                              default_value='false',
                              description='Set to false when not using past context.'))
    args.append(
        DeclareLaunchArgument('past_context_file',
                              default_value='',
                              description='Past context file to use. No need to specify when not using past context.'))
    args.append(
        DeclareLaunchArgument('max_context_limit',
                              default_value='100',
                              description='Maximum number of past context to keep.'))
    args.append(
        DeclareLaunchArgument('max_tokens',
                              default_value='1000',
                              description='Maximum number of tokens to use for each request.'))

    args.append(DeclareLaunchArgument('use_speech_action', default_value='true', description='Use sbgisen_speech'))

    args.append(
        DeclareLaunchArgument('setting_file',
                              default_value=[pkg_path, '/config/realtime_chat_setting.txt'],
                              description='Setting file.'))

    args.append(
        DeclareLaunchArgument('use_input_topic', default_value='false', description='Use topic to input audio source'))

    args.append(
        DeclareLaunchArgument('use_history', default_value='true', description='Use conversation history to chat.'))

    args.append(
        DeclareLaunchArgument('history_file',
                              default_value=PathJoinSubstitution([pkg_path, 'resource', 'history', 'history.jsonl']),
                              description='History file path(jsonl).'))

    args.append(DeclareLaunchArgument('use_tools', default_value='true', description='Weather use function call.'))

    args.append(
        DeclareLaunchArgument('tool_names', default_value="['horoscope', 'weather']", description='function names'))
    args.append(
        DeclareLaunchArgument('tools.horoscope.python_path',
                              default_value=[pkg_path, 'config/tools/horoscope/horoscope.py'],
                              description='python_file_path'))
    args.append(
        DeclareLaunchArgument('tools.horoscope.yaml_path',
                              default_value=[pkg_path, 'config/tools/horoscope/horoscope.yaml'],
                              description='yaml_file_path'))
    args.append(
        DeclareLaunchArgument('tools.weather.python_path',
                              default_value=[pkg_path, 'config/tools/weather/weather.py'],
                              description='python_file_path'))
    args.append(
        DeclareLaunchArgument('tools.weather.yaml_path',
                              default_value=[pkg_path, 'config/tools/weather/weather.yaml'],
                              description='yaml_file_path'))

    args.append(DeclareLaunchArgument('start_enable', default_value='false', description='Start with API Enable.'))

    return LaunchDescription(args + [OpaqueFunction(function=launch_setup)])
