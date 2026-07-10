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
"""GPT会話履歴・トークン概算のロジック (ROS非依存).

GPTClient から切り出した履歴組み立て・トリミング・トークン概算のロジックと、
realtime_gpt_chat が使う jsonl 履歴の整形・パース。
画像はエンコード済みの data URL 文字列として受け取る。
"""

import json
import pathlib
from typing import Dict, List, Optional


def approx_token_count(messages: List[Dict]) -> int:
    """メッセージ列のトークン数を概算する (約4文字 = 1トークン)."""
    total = 0
    for msg in messages:
        content = msg['content']
        if isinstance(content, list):
            for block in content:
                if block['type'] == 'input_text':
                    total += len(block['text']) // 4
        else:
            total += len(str(content)) // 4
    return total


def build_input(system_prompt: str, history: List[Dict]) -> List[Dict]:
    """System プロンプト + 履歴から API 入力メッセージ列を組み立てる."""
    messages = []
    if system_prompt:
        messages.append({'role': 'system', 'content': system_prompt})
    messages.extend(history)
    return messages


def trim_history(history: List[Dict], system_prompt: str, max_tokens: int) -> None:
    """max_tokens を超える間、古い履歴から順に削除する (in-place)."""
    messages = build_input(system_prompt, history)
    while approx_token_count(messages) > max_tokens and len(history) > 1:
        history.pop(0)
        messages = build_input(system_prompt, history)


def make_context_entry(
    role: str,
    text: Optional[str] = None,
    image_data_urls: Optional[List[str]] = None,
    detail: str = 'auto',
) -> Dict:
    """履歴に追加するエントリを組み立てる. text がファイルパスなら内容を読み込む."""
    content_blocks = []

    if text:
        if pathlib.Path(text).is_file():
            text = pathlib.Path(text).read_text(encoding='utf-8')

        content_blocks.append({'type': 'input_text', 'text': text})

    if image_data_urls:
        for image_url in image_data_urls:
            content_blocks.append({
                'type': 'input_image',
                'image_url': image_url,
                'detail': detail,
            })

    return {'role': role, 'content': content_blocks if content_blocks else text}


def format_history_entry(role: str, content: str, timestamp: str) -> str:
    """JSONL 履歴ファイルに追記する 1 行を組み立てる (改行付き)."""
    return json.dumps({'timestamp': timestamp, 'role': role, 'content': content}, ensure_ascii=False) + '\n'


def parse_history_lines(lines: List[str]) -> List[Dict]:
    """JSONL 履歴の行リストをパースする (壊れた行はスキップ)."""
    history: List[Dict] = []
    for line in lines:
        try:
            history.append(json.loads(line.strip()))
        except json.JSONDecodeError:
            continue
    return history
