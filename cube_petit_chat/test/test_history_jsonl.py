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
"""history_logic の jsonl 履歴ヘルパの単体テスト (ROS非依存)."""

import json

from cube_petit_chat.nodes.util.history_logic import format_history_entry
from cube_petit_chat.nodes.util.history_logic import parse_history_lines


class TestFormatHistoryEntry:

    def test_single_json_line_with_newline(self) -> None:
        line = format_history_entry('user', 'こんにちは', '2026-07-09T01:23:45')
        assert line.endswith('\n')
        assert json.loads(line) == {'timestamp': '2026-07-09T01:23:45', 'role': 'user', 'content': 'こんにちは'}

    def test_not_ascii_escaped(self) -> None:
        """日本語をエスケープせずそのまま書く (従来挙動: ensure_ascii=False)."""
        line = format_history_entry('assistant', 'おはよう', 't')
        assert 'おはよう' in line


class TestParseHistoryLines:

    def test_roundtrip(self) -> None:
        lines = [
            format_history_entry('user', 'やあ', 't1'),
            format_history_entry('assistant', 'こんにちは', 't2'),
        ]
        history = parse_history_lines(lines)
        assert [item['role'] for item in history] == ['user', 'assistant']
        assert history[0]['content'] == 'やあ'

    def test_broken_lines_are_skipped(self) -> None:
        lines = ['{"role": "user", "content": "ok"}\n', 'broken line\n', '']
        history = parse_history_lines(lines)
        assert history == [{'role': 'user', 'content': 'ok'}]
