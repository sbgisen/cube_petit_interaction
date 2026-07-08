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
"""realtime_gpt_chat ノードを構成するモジュール群.

- protocol: OpenAI Realtime API のイベント組み立て・解釈 (純粋関数)
- session: WebSocket 接続と送受信タスクの管理 (ROS 非依存)
- audio_io: sounddevice による音声入出力 (ROS 非依存)
- tools: GPT ツール (function calling) の読み込みと実行 (ROS 非依存)
"""

from typing import Protocol


class LoggerLike(Protocol):
    """rclpy の Logger と互換の最小ロガーインターフェース (ROS 非依存のための抽象)."""

    def info(self, message: str) -> None:
        """情報ログを出力する."""
        ...

    def warn(self, message: str) -> None:
        """警告ログを出力する."""
        ...

    def error(self, message: str) -> None:
        """エラーログを出力する."""
        ...
