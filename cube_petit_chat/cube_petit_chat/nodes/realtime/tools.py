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
"""GPT ツール (function calling) の読み込みと実行 (ROS 非依存).

ツール定義 YAML の読み込み、ツール実装 (.py) からの関数取得、引数パース付きの実行を担う。
どのツールを読むか (パラメータ解決) はノード側が行う。
"""

import importlib.util
from typing import Callable, Dict

from cube_petit_chat.nodes.realtime.protocol import parse_tool_arguments


def load_tool_yaml(yaml_path: str) -> Dict:
    """ツール定義 YAML を読み込む.

    Args:
        yaml_path: ツール定義 YAML のパス。

    Returns:
        YAML の内容 (dict)。
    """
    # PyYAML の無い環境 (CI のユニットテスト) でも本モジュールを import できるよう遅延 import する
    import yaml
    with open(yaml_path, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)


def load_tool_function(tool_name: str, py_path: str) -> Callable:
    """ツール実装 (.py) から tool_name と同名の関数を読み込む.

    Args:
        tool_name: ツール名 (モジュール名・関数名として使う)。
        py_path: ツール実装 Python ファイルのパス。

    Returns:
        読み込んだ関数。
    """
    spec = importlib.util.spec_from_file_location(tool_name, py_path)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return getattr(module, tool_name)


async def run_tool(tool_function: Callable, raw_args: object) -> object:
    """引数をパースしてツールを実行し、結果を返す.

    Args:
        tool_function: 実行する async ツール関数。
        raw_args: ツール呼び出しの引数 (JSON 文字列またはパース済みの値)。

    Returns:
        ツールの実行結果。
    """
    return await tool_function(parse_tool_arguments(raw_args))
