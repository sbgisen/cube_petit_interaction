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
from launch.actions import GroupAction
from launch.actions import OpaqueFunction
from launch.launch_context import LaunchContext
from launch.substitutions import EnvironmentVariable
from launch.substitutions import LaunchConfiguration
from launch.substitutions import PathJoinSubstitution
from launch_ros.actions import Node
from launch_ros.actions import PushRosNamespace
from launch_ros.substitutions import FindPackageShare


def launch_setup(context: LaunchContext) -> list:
    """Configure Azure-related parameters if 'use_azure' is true."""
    parameters = {
        'robot': LaunchConfiguration('robot'),
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
        'use_gpt_tools': LaunchConfiguration('use_gpt_tools'),
        'gpt_tool_names': LaunchConfiguration('gpt_tool_names'),
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

    gpt_nodes = []
    gpt_tool_names_str = LaunchConfiguration('gpt_tool_names').perform(context)
    try:
        gpt_tool_names = ast.literal_eval(gpt_tool_names_str)
        if not isinstance(gpt_tool_names, list):
            gpt_tool_names = [str(gpt_tool_names)]
    except Exception:
        gpt_tool_names = [n.strip() for n in gpt_tool_names_str.split(',') if n.strip()]

    for gpt_tool_name in gpt_tool_names:
        if not gpt_tool_name:
            continue

        pkg_arg_name = f'gpt_tools.{gpt_tool_name}.package'
        try:
            pkg_name = LaunchConfiguration(pkg_arg_name).perform(context)
            if not pkg_name:
                pkg_name = 'cube_petit_chat'
        except Exception:
            pkg_name = 'cube_petit_chat'

        pkg_share_path = FindPackageShare(pkg_name).perform(context)
        py_path = str(
            PathJoinSubstitution([pkg_share_path, 'config', 'gpt_tools', gpt_tool_name,
                                  f'{gpt_tool_name}.py']).perform(context))
        yaml_path = str(
            PathJoinSubstitution([pkg_share_path, 'config', 'gpt_tools', gpt_tool_name,
                                  f'{gpt_tool_name}.yaml']).perform(context))
        output_py_path = str(
            PathJoinSubstitution([pkg_share_path, 'config', 'gpt_tools', gpt_tool_name,
                                  f'{gpt_tool_name}_output.py']).perform(context))
        parameters[f'gpt_tools.{gpt_tool_name}.output_python_path'] = output_py_path
        parameters[f'gpt_tools.{gpt_tool_name}.python_path'] = py_path
        parameters[f'gpt_tools.{gpt_tool_name}.yaml_path'] = yaml_path
        parameters[f'gpt_tools.{gpt_tool_name}.package'] = pkg_name

        instruction_path = LaunchConfiguration(f'gpt_tools.{gpt_tool_name}.setting_path')

        gpt_nodes.append(
            GroupAction(actions=[
                PushRosNamespace(gpt_tool_name),
                Node(package='sbgisen_conversation',
                     executable='gpt_conversation',
                     name='chatter',
                     output='screen',
                     parameters=[{
                         'api_key': LaunchConfiguration('api_key').perform(context),
                         'model': 'gpt-4.1-mini',
                         'instructions_file': instruction_path,
                         'enable_web_search': True,
                         'max_tokens': 1000,
                         'max_turns': 2,
                         'structured_output_file': output_py_path,
                     }])
            ]))
    realtime_node = GroupAction(actions=[
        PushRosNamespace(LaunchConfiguration('robot')),
        Node(
            package='cube_petit_chat',
            executable='realtime_gpt_chat',
            name='realtime_gpt_chat',
            output='screen',
            parameters=[parameters],
        )
    ])
    return [realtime_node] + gpt_nodes


def generate_launch_description() -> LaunchDescription:
    """Generate launch descriptions.

    Returns:
        Launch descriptions
    """
    args = []
    pkg_path = FindPackageShare('cube_petit_chat')
    # arg list
    args.append(DeclareLaunchArgument('robot', default_value='cube_petit_orange', description='Robot namespace.'))
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
    args.append(DeclareLaunchArgument('use_gpt_tools', default_value='true', description='Weather use function call.'))

    args.append(
        DeclareLaunchArgument('tool_names',
                              default_value="['horoscope', 'weather', 'memory_voice', 'memory_name']",
                              description='function names'))
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
    args.append(
        DeclareLaunchArgument('tools.memory_voice.python_path',
                              default_value=[pkg_path, 'config/tools/memory_voice/memory_voice.py'],
                              description='python_file_path'))
    args.append(
        DeclareLaunchArgument('tools.memory_voice.yaml_path',
                              default_value=[pkg_path, 'config/tools/memory_voice/memory_voice.yaml'],
                              description='yaml_file_path'))
    args.append(
        DeclareLaunchArgument('tools.memory_name.python_path',
                              default_value=[pkg_path, 'config/tools/memory_name/memory_name.py'],
                              description='python_file_path'))
    args.append(
        DeclareLaunchArgument('tools.memory_name.yaml_path',
                              default_value=[pkg_path, 'config/tools/memory_name/memory_name.yaml'],
                              description='yaml_file_path'))

    # args.append(DeclareLaunchArgument('gpt_tool_names', default_value="['gpt_chat']", description='function names'))
    args.append(DeclareLaunchArgument('gpt_tool_names', default_value="['']", description='function names'))
    args.append(
        DeclareLaunchArgument('gpt_tools.gpt_chat.python_path',
                              default_value=[pkg_path, 'config/gpt_tools/gpt_chat/gpt_chat.py'],
                              description='python_file_path'))
    args.append(
        DeclareLaunchArgument('gpt_tools.gpt_chat.output_python_path',
                              default_value=[pkg_path, 'config/gpt_tools/gpt_chat/gpt_chat_output.py'],
                              description='python_file_path'))

    args.append(
        DeclareLaunchArgument('gpt_tools.gpt_chat.yaml_path',
                              default_value=[pkg_path, 'config/gpt_tools/gpt_chat/gpt_chat.yaml'],
                              description='yaml_file_path'))
    args.append(
        DeclareLaunchArgument('gpt_tools.gpt_chat.setting_path',
                              default_value=[pkg_path, '/config/gpt_tools/gpt_chat/gpt_chat.txt'],
                              description='setting_file_path'))

    args.append(DeclareLaunchArgument('start_enable', default_value='true', description='Start with API Enable.'))

    return LaunchDescription(args + [OpaqueFunction(function=launch_setup)])
