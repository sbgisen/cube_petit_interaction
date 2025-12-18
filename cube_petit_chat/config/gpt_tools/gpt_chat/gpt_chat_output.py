#!/usr/bin/env python

# Copyright (c) 2025 SoftBank Corp.
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

from pydantic import BaseModel


class OutputContext(BaseModel):
    """Class to represent the output context for talking agent."""

    speech_phrase: str
    """ロボットが話すフレーズ。箇条書きにせず、会話の一部として自然な文章で出力してください。引用情報、URLなどは不要なので含めないでください。"""

    end_conversation: bool
    """会話が終了した場合はtrueにしてください。"""
