#!/usr/bin/env python

# Copyright (c) 2025 SoftBank Corp.
#
# <<licensetext>>

from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node


def generate_launch_description() -> list:

    db_path_arg = DeclareLaunchArgument('db_path', default_value='users.db', description='Path to user database')

    db_path = LaunchConfiguration('db_path')

    node = Node(package='memory_person',
                executable='user_store_node',
                name='user_store_node',
                output='screen',
                parameters=[{
                    'db_path': db_path
                }])

    return LaunchDescription([db_path_arg, node])
