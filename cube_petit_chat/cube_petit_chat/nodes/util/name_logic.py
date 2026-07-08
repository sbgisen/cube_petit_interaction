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
"""ロボット名からグローバル名を組み立てるロジック (ROS非依存).

speech_action_server は名前空間解決に頼らず絶対名で指定する
(相対名では動作しなかったため、絶対名指定を維持している。2ed17a0 参照)。
"""

DEFAULT_ROBOT = 'cube_petit_orange'


def speech_action_server_name(robot: str = DEFAULT_ROBOT) -> str:
    """ロボット名から speech_action_server の絶対アクション名を組み立てる.

    Args:
        robot: ロボットの名前空間 (例: 'cube_petit_orange')。

    Returns:
        '/<robot>/speech_action_server' 形式の絶対名。
    """
    return f'/{robot}/speech_action_server'
