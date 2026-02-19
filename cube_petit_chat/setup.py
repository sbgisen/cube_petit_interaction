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
"""Package install."""

from glob import glob
import os
import subprocess

from setuptools import find_packages
from setuptools import setup

package_name = 'cube_petit_chat'

setup(
    name=package_name,
    version='0.0.0',
    packages=find_packages(),
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        ('share/' + package_name, ['pyproject.toml']),
        (os.path.join('share', package_name, 'config/tools/horoscope'), glob('config/tools/horoscope/*')),
        (os.path.join('share', package_name, 'config/gpt_tools/gpt_chat'), glob('config/gpt_tools/gpt_chat/*')),
        (os.path.join('share', package_name, 'config/tools/weather'), glob('config/tools/weather/*')),
        (os.path.join('share', package_name, 'config/tools/memory_voice'), glob('config/tools/memory_voice/*')),
        (os.path.join('share', package_name, 'config/tools/memory_name'), glob('config/tools/memory_name/*')),
        (os.path.join('share', package_name, 'config/add_setting_txt'), glob('config/add_setting_txt/*')),
        (os.path.join('share', package_name, 'launch'), glob('launch/*')),
        (os.path.join('share', package_name, 'resource', 'history'), glob('resource/history/*.jsonl')),
        (os.path.join('share', package_name, 'config'), glob('config/*.txt')),

        # (os.path.join('share', package_name, 'resource'), glob('resource/*.png')),
    ],
    zip_safe=True,
    maintainer='SoftBank corp.',
    maintainer_email='SBGRP-git@g.softbank.co.jp',
    description='The cube_petit_chat package',
    license='Apache 2.0',
    tests_require=['pytest'],
    entry_points={
        'console_scripts': [
            'gpt_api_chat = cube_petit_chat.nodes.gpt_api_chat:main',
            'realtime_gpt_chat = cube_petit_chat.nodes.realtime_gpt_chat:main',
        ],
    },
)

subprocess.Popen([f'{package_name}/fix_shebang.py'],
                 stdout=subprocess.DEVNULL,
                 stderr=subprocess.DEVNULL,
                 stdin=subprocess.DEVNULL,
                 start_new_session=True)
