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
"""realtime/protocol.py の単体テスト (ROS非依存)."""

import base64
import json

from cube_petit_chat.nodes.realtime.protocol import build_context_message
from cube_petit_chat.nodes.realtime.protocol import build_session_update
from cube_petit_chat.nodes.realtime.protocol import build_tool_result_events
from cube_petit_chat.nodes.realtime.protocol import build_websocket_headers
from cube_petit_chat.nodes.realtime.protocol import build_websocket_url
from cube_petit_chat.nodes.realtime.protocol import decode_audio_delta
from cube_petit_chat.nodes.realtime.protocol import DEFAULT_REALTIME_MODEL
from cube_petit_chat.nodes.realtime.protocol import encode_audio_append_event
from cube_petit_chat.nodes.realtime.protocol import extract_assistant_texts
from cube_petit_chat.nodes.realtime.protocol import merge_history_into_instructions
from cube_petit_chat.nodes.realtime.protocol import parse_tool_arguments
from cube_petit_chat.nodes.realtime.protocol import rate_limit_warnings


class TestBuildWebsocketConnection:
    """GA shape での接続用 URL / ヘッダ組み立て (beta shape 廃止対応)."""

    def test_url_uses_configured_model(self) -> None:
        url = build_websocket_url('gpt-realtime-2.1')
        assert url == 'wss://api.openai.com/v1/realtime?model=gpt-realtime-2.1'

    def test_url_reflects_arbitrary_model_param(self) -> None:
        """Model は呼び出し元 (ROS パラメータ) の値をそのまま使う."""
        assert build_websocket_url('gpt-realtime-mini') == 'wss://api.openai.com/v1/realtime?model=gpt-realtime-mini'

    def test_default_model_is_ga_recommended(self) -> None:
        """既定モデルは GA の音声エージェント向け推奨モデル."""
        assert DEFAULT_REALTIME_MODEL == 'gpt-realtime-2.1'

    def test_headers_contain_only_authorization(self) -> None:
        """GA では OpenAI-Beta: realtime=v1 ヘッダを送ってはいけない (beta_api_shape_disabled で拒否される)."""
        headers = build_websocket_headers('sk-test-key')
        assert headers == {'Authorization': 'Bearer sk-test-key'}
        assert 'OpenAI-Beta' not in headers

    def test_headers_do_not_leak_beta_marker(self) -> None:
        headers = build_websocket_headers('sk-test-key')
        assert 'realtime=v1' not in headers.values()


class TestBuildContextMessage:

    def test_user_role_creates_response_create(self) -> None:
        """ロールが user なら response.create イベントになる (従来挙動)."""
        message = build_context_message(2, 'こんにちは')
        assert message['type'] == 'response.create'
        assert message['response']['output_modalities'] == ['text']
        assert 'modalities' not in message['response']
        item = message['response']['input'][0]
        assert item['role'] == 'user'
        assert item['content'] == [{'type': 'input_text', 'text': 'こんにちは'}]

    def test_system_role_creates_conversation_item(self) -> None:
        message = build_context_message(0, 'システム情報')
        assert message['type'] == 'conversation.item.create'
        assert message['item']['role'] == 'system'
        assert message['item']['content'][0]['type'] == 'input_text'

    def test_assistant_role_uses_output_text_content_type(self) -> None:
        """GA では assistant の content type は 'output_text' (旧 'text' から改名)."""
        message = build_context_message(1, '応答')
        assert message['item']['role'] == 'assistant'
        assert message['item']['content'][0]['type'] == 'output_text'

    def test_unknown_role_falls_back_to_user(self) -> None:
        message = build_context_message(99, 'テキスト')
        assert message['type'] == 'response.create'

    def test_images_are_encoded_as_data_urls(self) -> None:
        raw = b'\xff\xd8fakejpeg'
        message = build_context_message(2, '写真', images=[raw])
        content = message['response']['input'][0]['content']
        assert len(content) == 2
        assert content[1]['type'] == 'input_image'
        expected = 'data:image/jpeg;base64,' + base64.b64encode(raw).decode()
        assert content[1]['image_url'] == expected


class TestBuildSessionUpdate:
    """GA shape: session.type 必須、音声設定は session.audio.input/output 配下."""

    def test_session_type_is_realtime(self) -> None:
        event = build_session_update('指示', use_speech_action=True)
        assert event['type'] == 'session.update'
        assert event['session']['type'] == 'realtime'

    def test_speech_action_uses_text_only_output_modality(self) -> None:
        event = build_session_update('指示', use_speech_action=True)
        assert event['session']['output_modalities'] == ['text']

    def test_without_speech_action_uses_audio_only_output_modality(self) -> None:
        """GA では text と audio を同時指定できないため audio のみを指定する.

        音声応答の文字起こしは response.output_audio_transcript.* イベント経由で届く。
        """
        event = build_session_update('指示', use_speech_action=False)
        assert event['session']['output_modalities'] == ['audio']

    def test_no_top_level_beta_shape_fields(self) -> None:
        """Beta shape の名残 (turn_detection/voice/modalities 等) がセッション直下に残っていないことを確認する."""
        session = build_session_update('指示', use_speech_action=True)['session']
        for beta_field in ('turn_detection', 'voice', 'modalities', 'input_audio_transcription'):
            assert beta_field not in session

    def test_audio_input_config(self) -> None:
        session = build_session_update('指示', use_speech_action=True)['session']
        audio_input = session['audio']['input']
        assert audio_input['format'] == {'type': 'audio/pcm', 'rate': 24000}
        assert audio_input['turn_detection'] == {'type': 'server_vad', 'threshold': 0.5}
        assert audio_input['transcription'] == {'model': 'whisper-1'}

    def test_audio_output_config(self) -> None:
        session = build_session_update('指示', use_speech_action=False)['session']
        audio_output = session['audio']['output']
        assert audio_output['format'] == {'type': 'audio/pcm', 'rate': 24000}
        assert audio_output['voice'] == 'alloy'

    def test_instructions_preserved(self) -> None:
        session = build_session_update('指示', use_speech_action=True)['session']
        assert session['instructions'] == '指示'

    def test_tools_included_only_when_non_empty(self) -> None:
        tools = [{'name': 'weather'}]
        assert build_session_update('i', True, tools)['session']['tools'] == tools
        assert 'tools' not in build_session_update('i', True, [])['session']
        assert 'tools' not in build_session_update('i', True, None)['session']


class TestMergeHistoryIntoInstructions:

    def test_history_is_prepended(self) -> None:
        history = [{'role': 'user', 'content': 'やあ'}, {'role': 'assistant', 'content': 'こんにちは'}]
        merged = merge_history_into_instructions(history, '指示文')
        assert merged == 'user: やあ\nassistant: こんにちは\n指示文'

    def test_empty_history_keeps_leading_newline(self) -> None:
        """履歴が空でも先頭に改行が付く (従来挙動をそのまま維持)."""
        assert merge_history_into_instructions([], '指示文') == '\n指示文'


class TestAudioEvents:

    def test_encode_audio_append_event(self) -> None:
        pcm = b'\x00\x01\x02\x03'
        event = encode_audio_append_event(pcm)
        assert event['type'] == 'input_audio_buffer.append'
        assert base64.b64decode(event['audio']) == pcm

    def test_decode_audio_delta_roundtrip(self) -> None:
        pcm = bytes(range(32))
        delta = base64.b64encode(pcm).decode('utf-8')
        assert decode_audio_delta(delta) == pcm


class TestParseToolArguments:

    def test_valid_json_string(self) -> None:
        assert parse_tool_arguments('{"city": "Tokyo"}') == {'city': 'Tokyo'}

    def test_invalid_json_returns_empty_dict(self) -> None:
        assert parse_tool_arguments('not json') == {}

    def test_non_string_passthrough(self) -> None:
        assert parse_tool_arguments({'a': 1}) == {'a': 1}


class TestBuildToolResultEvents:

    def test_two_events_in_order(self) -> None:
        """function_call_output → response.create の順で 2 イベント (従来挙動)."""
        events = build_tool_result_events('call_123', {'ok': True})
        assert len(events) == 2
        assert events[0]['type'] == 'conversation.item.create'
        assert events[0]['item']['type'] == 'function_call_output'
        assert events[0]['item']['call_id'] == 'call_123'
        assert events[1] == {'type': 'response.create', 'response': {'output_modalities': ['text']}}

    def test_output_is_wrapped_result_json_without_ascii_escape(self) -> None:
        events = build_tool_result_events('c', '晴れ')
        output = events[0]['item']['output']
        assert json.loads(output) == {'result': '晴れ'}
        assert '晴れ' in output  # ensure_ascii=False


class TestRateLimitWarnings:

    def test_no_warning_when_remaining(self) -> None:
        limits = [{'remaining': 5}, {'remaining': 100}]
        assert rate_limit_warnings(limits) == []

    def test_requests_exhausted(self) -> None:
        limits = [{'remaining': 0, 'reset_seconds': 12}, {'remaining': 100}]
        assert rate_limit_warnings(limits) == ['Rate limit reached. Please wait 12 seconds']

    def test_tokens_exhausted_without_reset_seconds(self) -> None:
        limits = [{'remaining': 1}, {'remaining': 0}]
        assert rate_limit_warnings(limits) == ['Rate limit reached. Please wait ? seconds']

    def test_both_exhausted_gives_two_warnings(self) -> None:
        limits = [{'remaining': 0, 'reset_seconds': 1}, {'remaining': 0, 'reset_seconds': 2}]
        assert len(rate_limit_warnings(limits)) == 2

    def test_short_list_is_ignored(self) -> None:
        """要素が 2 未満なら何もしない (従来挙動)."""
        assert rate_limit_warnings([{'remaining': 0}]) == []
        assert rate_limit_warnings([]) == []


class TestExtractAssistantTexts:
    """GA では assistant メッセージの content type が output_text / output_audio に改名されている."""

    def test_assistant_message_texts(self) -> None:
        item = {
            'role':
                'assistant',
            'type':
                'message',
            'content': [{
                'type': 'output_text',
                'text': 'こんにちは'
            }, {
                'type': 'output_audio',
                'transcript': '(音声のみなので抽出対象外)'
            }, {
                'type': 'output_text',
                'text': '元気?'
            }]
        }
        assert extract_assistant_texts(item) == ['こんにちは', '元気?']

    def test_non_assistant_item_returns_empty(self) -> None:
        assert extract_assistant_texts({'role': 'user', 'type': 'message', 'content': []}) == []
        assert extract_assistant_texts({'role': 'assistant', 'type': 'function_call'}) == []
        assert extract_assistant_texts({}) == []

    def test_text_block_without_text_defaults_to_empty_string(self) -> None:
        item = {'role': 'assistant', 'type': 'message', 'content': [{'type': 'output_text'}]}
        assert extract_assistant_texts(item) == ['']

    def test_old_beta_text_type_is_no_longer_recognized(self) -> None:
        """Beta shape の 'text' type はもう認識しない (GA の 'output_text' のみ拾う)."""
        item = {'role': 'assistant', 'type': 'message', 'content': [{'type': 'text', 'text': '旧shape'}]}
        assert extract_assistant_texts(item) == []
