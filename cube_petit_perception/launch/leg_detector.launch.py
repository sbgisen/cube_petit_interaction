#!/usr/bin/env python

# Copyright (c) 2024 SoftBank Corp.
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
from launch.actions import GroupAction
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.actions import PushROSNamespace
from launch_ros.substitutions import FindPackageShare


def generate_launch_description() -> LaunchDescription:
    """Generate launch descriptions.

    Returns:
        Launch descriptions
    """
    args = []
    args.append(DeclareLaunchArgument('robot', default_value='cube_petit_orange', description='Robot namespace.'))

    leg_detector = GroupAction(actions=[
        PushROSNamespace('object_detection'),
        GroupAction(actions=[
            PushROSNamespace('laser'),
            Node(package='leg_detector',
                 executable='leg_detector',
                 name='detector',
                 arguments=[[FindPackageShare('leg_detector'), '/config/trained_leg_detector.yaml']],
                 remappings=[
                     ('scan', ['/', LaunchConfiguration('robot'), '/scan']),
                     ('leg_tracker_measurements', 'leg_position'),
                     ('people_tracker_measurements', 'pair_of_legs_position'),
                     ('visualization_marker', 'marker'),
                 ],
                #  parameters=[{
                #      'fixed_frame': 'base_link',
                #      'connection_threshold': 0.06,
                #      'leg_reliability_limit': 0.21,
                #      'leg_pair_separation': 0.5,
                #      'use_sim_time': False,
                #  }]),
                parameters=[{
                     'fixed_frame': 'pacecat_link',
                     'connected_thresh': 0.15,
                     'min_points_per_group': 2,
                     'leg_reliability_limit': -1.0,

                     'leg_pair_separation': 0.45,
                     'max_meas_jump': 1.0,
                     'max_track_jump': 1.2,
                     'no_observation_timeout': 1.0,
                     'max_second_leg_age': 3.0,

                     'use_sim_time': False,
                 }]),
        ])
    ])

    return LaunchDescription(args + [leg_detector])
