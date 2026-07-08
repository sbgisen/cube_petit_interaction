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
"""name_logic の単体テスト (ROS非依存)."""

from cube_petit_chat.nodes.util.name_logic import DEFAULT_ROBOT
from cube_petit_chat.nodes.util.name_logic import speech_action_server_name


class TestSpeechActionServerName:

    def test_default_matches_previous_hardcoded_literal(self) -> None:
        """デフォルト値では従来ハードコードされていた絶対名と完全一致する (挙動維持の保証)."""
        assert speech_action_server_name() == '/cube_petit_orange/speech_action_server'

    def test_default_robot_constant(self) -> None:
        assert DEFAULT_ROBOT == 'cube_petit_orange'
        assert speech_action_server_name(DEFAULT_ROBOT) == '/cube_petit_orange/speech_action_server'

    def test_other_robot(self) -> None:
        assert speech_action_server_name('cube_petit_pink') == '/cube_petit_pink/speech_action_server'

    def test_returns_absolute_name(self) -> None:
        """名前空間解決に頼らない絶対名 (先頭 '/') であること."""
        assert speech_action_server_name('any_robot').startswith('/')
