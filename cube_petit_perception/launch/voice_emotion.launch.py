#!/usr/bin/env python

# Copyright (c) 2026 SoftBank Corp.
# 
# <<licensetext>>

from launch import LaunchDescription
from launch.actions import GroupAction
from launch_ros.actions import Node, PushRosNamespace
from launch.substitutions import EnvironmentVariable


def generate_launch_description():

    return LaunchDescription([

        GroupAction([
            PushRosNamespace("cube_petit_pink"),
            Node(
                package="cube_petit_perception",
                executable="voice_emotion_node",
                name="voice_emotion_node",
                output="screen",
                parameters=[{
                    "api_key": EnvironmentVariable("EMPATH_API"),
                    "start_enable": True,
                }],
            )
        ])

    ])
