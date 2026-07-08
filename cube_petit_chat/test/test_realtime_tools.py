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
"""realtime/tools.py の単体テスト (ROS非依存)."""

import asyncio
import pathlib

import pytest

from cube_petit_chat.nodes.realtime.tools import load_tool_function
from cube_petit_chat.nodes.realtime.tools import load_tool_yaml
from cube_petit_chat.nodes.realtime.tools import run_tool

TOOL_SOURCE = """
async def my_tool(args):
    return {'echo': args}
"""


class TestLoadToolFunction:

    def test_loads_function_named_after_tool(self, tmp_path: pathlib.Path) -> None:
        py_path = tmp_path / 'my_tool.py'
        py_path.write_text(TOOL_SOURCE, encoding='utf-8')
        function = load_tool_function('my_tool', str(py_path))
        assert callable(function)
        assert asyncio.run(function({'a': 1})) == {'echo': {'a': 1}}

    def test_missing_function_raises(self, tmp_path: pathlib.Path) -> None:
        py_path = tmp_path / 'other.py'
        py_path.write_text('x = 1\n', encoding='utf-8')
        with pytest.raises(AttributeError):
            load_tool_function('other', str(py_path))

    def test_missing_file_raises(self, tmp_path: pathlib.Path) -> None:
        with pytest.raises(Exception):
            load_tool_function('nope', str(tmp_path / 'nope.py'))


class TestLoadToolYaml:

    def test_loads_yaml_definition(self, tmp_path: pathlib.Path) -> None:
        pytest.importorskip('yaml')
        yaml_path = tmp_path / 'my_tool.yaml'
        yaml_path.write_text('name: my_tool\ntype: function\n', encoding='utf-8')
        assert load_tool_yaml(str(yaml_path)) == {'name': 'my_tool', 'type': 'function'}


class TestRunTool:

    def test_parses_json_string_arguments(self, tmp_path: pathlib.Path) -> None:
        py_path = tmp_path / 'my_tool.py'
        py_path.write_text(TOOL_SOURCE, encoding='utf-8')
        function = load_tool_function('my_tool', str(py_path))
        result = asyncio.run(run_tool(function, '{"city": "Tokyo"}'))
        assert result == {'echo': {'city': 'Tokyo'}}

    def test_invalid_json_arguments_become_empty_dict(self, tmp_path: pathlib.Path) -> None:
        """引数が JSON として不正なら空 dict で実行する (従来挙動)."""
        py_path = tmp_path / 'my_tool.py'
        py_path.write_text(TOOL_SOURCE, encoding='utf-8')
        function = load_tool_function('my_tool', str(py_path))
        result = asyncio.run(run_tool(function, 'not json'))
        assert result == {'echo': {}}
