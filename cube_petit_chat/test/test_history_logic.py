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
"""history_logic の単体テスト (ROS非依存)."""

import pathlib

from cube_petit_chat.nodes.util.history_logic import approx_token_count
from cube_petit_chat.nodes.util.history_logic import build_input
from cube_petit_chat.nodes.util.history_logic import make_context_entry
from cube_petit_chat.nodes.util.history_logic import trim_history


class TestApproxTokenCount:

    def test_empty_messages(self) -> None:
        assert approx_token_count([]) == 0

    def test_string_content(self) -> None:
        """文字列コンテンツは len // 4 で概算する."""
        messages = [{'role': 'user', 'content': 'a' * 40}]
        assert approx_token_count(messages) == 10

    def test_block_content_counts_only_input_text(self) -> None:
        """ブロック形式は input_text のみ数え、画像ブロックは無視する."""
        messages = [{
            'role':
                'user',
            'content': [
                {
                    'type': 'input_text',
                    'text': 'a' * 40
                },
                {
                    'type': 'input_image',
                    'image_url': 'x' * 4000,
                    'detail': 'auto'
                },
            ],
        }]
        assert approx_token_count(messages) == 10

    def test_multiple_messages_summed(self) -> None:
        messages = [
            {
                'role': 'system',
                'content': 'a' * 8
            },
            {
                'role': 'user',
                'content': 'b' * 12
            },
        ]
        assert approx_token_count(messages) == 2 + 3

    def test_non_string_content_uses_str(self) -> None:
        """文字列以外のコンテンツは str() で数える."""
        messages = [{'role': 'user', 'content': None}]
        assert approx_token_count(messages) == len('None') // 4


class TestBuildInput:

    def test_system_prompt_prepended(self) -> None:
        history = [{'role': 'user', 'content': 'hi'}]
        messages = build_input('you are a robot', history)
        assert messages[0] == {'role': 'system', 'content': 'you are a robot'}
        assert messages[1:] == history

    def test_empty_system_prompt_omitted(self) -> None:
        history = [{'role': 'user', 'content': 'hi'}]
        messages = build_input('', history)
        assert messages == history

    def test_does_not_mutate_history(self) -> None:
        history = [{'role': 'user', 'content': 'hi'}]
        messages = build_input('sys', history)
        messages.append({'role': 'assistant', 'content': 'yo'})
        assert len(history) == 1


class TestTrimHistory:

    def test_under_limit_unchanged(self) -> None:
        history = [{'role': 'user', 'content': 'a' * 40}]
        trim_history(history, '', max_tokens=100)
        assert len(history) == 1

    def test_over_limit_pops_oldest(self) -> None:
        """上限超過時は古いものから削除される."""
        history = [
            {
                'role': 'user',
                'content': 'old' + 'a' * 400
            },
            {
                'role': 'assistant',
                'content': 'mid' + 'b' * 400
            },
            {
                'role': 'user',
                'content': 'new'
            },
        ]
        trim_history(history, '', max_tokens=150)
        assert len(history) == 2
        assert history[0]['content'].startswith('mid')
        assert history[-1]['content'] == 'new'

    def test_keeps_at_least_one_entry(self) -> None:
        """上限を超えていても直近 1 件は必ず残す."""
        history = [{'role': 'user', 'content': 'a' * 4000}]
        trim_history(history, '', max_tokens=10)
        assert len(history) == 1

    def test_system_prompt_counts_toward_budget(self) -> None:
        """System プロンプト分もトークン予算に含まれる."""
        history = [
            {
                'role': 'user',
                'content': 'a' * 40
            },  # 10 tokens
            {
                'role': 'user',
                'content': 'b' * 40
            },  # 10 tokens
        ]
        # system 40 文字 = 10 tokens。合計 30 > 25 なので先頭が削られる
        trim_history(history, 's' * 40, max_tokens=25)
        assert len(history) == 1
        assert history[0]['content'] == 'b' * 40

    def test_trims_in_place(self) -> None:
        history = [
            {
                'role': 'user',
                'content': 'a' * 400
            },
            {
                'role': 'user',
                'content': 'b' * 4
            },
        ]
        same = history
        trim_history(history, '', max_tokens=50)
        assert same is history
        assert len(history) == 1


class TestMakeContextEntry:

    def test_text_only(self) -> None:
        entry = make_context_entry('user', text='こんにちは')
        assert entry['role'] == 'user'
        assert entry['content'] == [{'type': 'input_text', 'text': 'こんにちは'}]

    def test_text_from_file_path(self, tmp_path: pathlib.Path) -> None:
        """Text が実在するファイルパスなら内容を読み込む."""
        f = tmp_path / 'prompt.txt'
        f.write_text('ファイルの中身', encoding='utf-8')
        entry = make_context_entry('user', text=str(f))
        assert entry['content'] == [{'type': 'input_text', 'text': 'ファイルの中身'}]

    def test_images_become_blocks(self) -> None:
        urls = ['data:image/jpeg;base64,AAA', 'data:image/jpeg;base64,BBB']
        entry = make_context_entry('user', text='見て', image_data_urls=urls, detail='low')
        blocks = entry['content']
        assert blocks[0] == {'type': 'input_text', 'text': '見て'}
        assert blocks[1] == {'type': 'input_image', 'image_url': urls[0], 'detail': 'low'}
        assert blocks[2] == {'type': 'input_image', 'image_url': urls[1], 'detail': 'low'}

    def test_no_text_no_images_content_is_none(self) -> None:
        """Text も画像もない場合 content は None (元実装と同じ)."""
        entry = make_context_entry('assistant')
        assert entry == {'role': 'assistant', 'content': None}

    def test_images_only(self) -> None:
        urls = ['data:image/jpeg;base64,AAA']
        entry = make_context_entry('user', image_data_urls=urls)
        assert entry['content'] == [
            {
                'type': 'input_image',
                'image_url': urls[0],
                'detail': 'auto'
            },
        ]
