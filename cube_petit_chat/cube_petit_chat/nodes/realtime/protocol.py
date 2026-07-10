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
"""OpenAI Realtime API のイベント組み立て・解釈ロジック (ROS 非依存・純粋関数).

WebSocket に送るイベント dict の生成と、受信イベントからの情報抽出だけを行う。
送受信そのものは session.py、ROS への反映はノード側が担う。
"""

import base64
import json
from typing import Dict, List, Optional

# AddContext.Request.role の値と Realtime API のロール名の対応
ROLE_MAP = {
    0: 'system',
    1: 'assistant',
    2: 'user',
}

# OpenAI Realtime API (GA) の推奨モデル。音声エージェント用途の既定値。
# https://developers.openai.com/api/docs/guides/realtime (Build a low-latency voice agent -> gpt-realtime-2.1)
DEFAULT_REALTIME_MODEL = 'gpt-realtime-2.1'

# 入出力とも 24kHz PCM16 固定 (audio_io.py 側のサンプルレートと一致させる)
_PCM_AUDIO_FORMAT = {'type': 'audio/pcm', 'rate': 24000}


def build_websocket_url(model: str) -> str:
    """OpenAI Realtime API (GA) への接続 URL を組み立てる.

    URL の形自体は beta 期から変わらないが、model は呼び出し元 (ROS パラメータ) 由来にする。

    Args:
        model: 接続する Realtime モデル名 (例: gpt-realtime-2.1)。

    Returns:
        wss://api.openai.com/v1/realtime?model=... の URL 文字列。
    """
    return f'wss://api.openai.com/v1/realtime?model={model}'


def build_websocket_headers(api_key: str) -> Dict[str, str]:
    """接続用 HTTP ヘッダを組み立てる.

    2026-05-12 に OpenAI が beta shape を廃止したため、`OpenAI-Beta: realtime=v1`
    ヘッダは付けない (付けると invalid_request_error.beta_api_shape_disabled で
    close code 4000 になる)。GA でも Authorization ヘッダのみで認証する。

    Args:
        api_key: OpenAI API キー。

    Returns:
        Authorization ヘッダのみを含む dict。
    """
    return {'Authorization': f'Bearer {api_key}'}


def build_context_message(role_id: int, context: str, images: Optional[List[bytes]] = None) -> Dict:
    """AddContext リクエストの内容から Realtime API へ送るイベントを組み立てる.

    Args:
        role_id: AddContext.Request.role の値 (0=system, 1=assistant, 2=user)。
        context: 追加するテキスト。
        images: JPEG バイト列のリスト (省略可)。

    Returns:
        user ロールなら response.create、それ以外なら conversation.item.create のイベント dict。
    """
    role = ROLE_MAP.get(role_id, 'user')
    if role == 'assistant':
        # GA では assistant メッセージの content type は 'text' ではなく 'output_text'。
        content_type = 'output_text'
    else:
        content_type = 'input_text'

    content: List[Dict] = [{'type': content_type, 'text': context}]
    for img_bytes in images or []:
        b64 = base64.b64encode(img_bytes).decode()
        content.append({
            'type': 'input_image',
            'image_url': f'data:image/jpeg;base64,{b64}',
        })

    if role == 'user':
        return {
            'type': 'response.create',
            'response': {
                # GA では response.create の modalities は output_modalities に改名された。
                'output_modalities': ['text'],
                'input': [{
                    'type': 'message',
                    'role': 'user',
                    'content': content,
                }]
            }
        }
    return {
        'type': 'conversation.item.create',
        'item': {
            'type': 'message',
            'role': role,
            'content': content,
        }
    }


def build_session_update(instructions: str, use_speech_action: bool, tools: Optional[List[Dict]] = None) -> Dict:
    """session.update イベントを組み立てる (GA shape).

    GA では session.type が必須になり、音声関連の設定はすべて session.audio.input /
    session.audio.output 配下に移動した (以前は turn_detection / voice / modalities /
    input_audio_transcription がすべてセッション直下だった)。
    また modalities は output_modalities に改名され、text と audio を同時に指定できなく
    なった (音声応答時は response.output_audio_transcript.* イベントで文字起こしが届く
    ので、テキストと音声を両方要求していた従来の実質的な効果は保たれる)。

    Args:
        instructions: セッションに適用する指示文。
        use_speech_action: True ならテキストのみ、False なら音声のモダリティ。
        tools: ツール定義のリスト (空/None なら tools キーを付けない)。

    Returns:
        session.update のイベント dict。
    """
    session: Dict = {
        'type': 'realtime',
        'output_modalities': ['text'] if use_speech_action else ['audio'],
        'instructions': instructions,
        'audio': {
            'input': {
                'format': _PCM_AUDIO_FORMAT,
                'turn_detection': {
                    'type': 'server_vad',
                    'threshold': 0.5,
                },
                'transcription': {
                    'model': 'whisper-1'
                },
            },
            'output': {
                'format': _PCM_AUDIO_FORMAT,
                'voice': 'alloy',
            },
        },
    }
    if tools:
        session['tools'] = tools
    return {'type': 'session.update', 'session': session}


def merge_history_into_instructions(history: List[Dict], instructions: str) -> str:
    """会話履歴を instructions の先頭に連結する.

    Args:
        history: {'role': ..., 'content': ...} 形式の履歴リスト。
        instructions: 元の指示文。

    Returns:
        履歴テキスト + 改行 + 指示文。
    """
    history_text = '\n'.join([f"{item['role']}: {item['content']}" for item in history])
    return history_text + '\n' + instructions


def encode_audio_append_event(audio_data: bytes) -> Dict:
    """PCM バイト列から input_audio_buffer.append イベントを組み立てる."""
    base64_audio = base64.b64encode(audio_data).decode('utf-8')
    return {'type': 'input_audio_buffer.append', 'audio': base64_audio}


def decode_audio_delta(delta: str) -> bytes:
    """response.output_audio.delta の base64 文字列を PCM バイト列に復号する (GA でイベント名が改名)."""
    return base64.b64decode(delta)


def parse_tool_arguments(raw_args: object) -> object:
    """ツール呼び出しの引数をパースする.

    Args:
        raw_args: JSON 文字列またはパース済みの値。

    Returns:
        パース結果。JSON として不正な文字列なら空 dict。
    """
    if not isinstance(raw_args, str):
        return raw_args
    try:
        return json.loads(raw_args)
    except json.JSONDecodeError:
        return {}


def build_tool_result_events(call_id: str, result: object) -> List[Dict]:
    """ツール実行結果を返すイベント列を組み立てる.

    Args:
        call_id: function call の call_id。
        result: ツールの実行結果。

    Returns:
        function_call_output と、続きの応答を促す response.create の 2 イベント。
    """
    return [
        {
            'type': 'conversation.item.create',
            'item': {
                'type': 'function_call_output',
                'call_id': call_id,
                'output': json.dumps({'result': result}, ensure_ascii=False)
            }
        },
        {
            'type': 'response.create',
            'response': {
                'output_modalities': ['text']
            }
        },
    ]


def rate_limit_warnings(rate_limits: List[Dict]) -> List[str]:
    """rate_limits.updated イベントの内容から警告文のリストを組み立てる.

    Args:
        rate_limits: rate_limits.updated イベントの rate_limits リスト。

    Returns:
        残量ゼロの項目に対する警告文のリスト (なければ空)。
    """
    warnings: List[str] = []
    if len(rate_limits) >= 2:
        remaining_requests = rate_limits[0].get('remaining', 1)
        remaining_tokens = rate_limits[1].get('remaining', 1)
        if remaining_requests == 0:
            reset_seconds = rate_limits[0].get('reset_seconds', '?')
            warnings.append(f'Rate limit reached. Please wait {reset_seconds} seconds')
        if remaining_tokens == 0:
            reset_seconds = rate_limits[1].get('reset_seconds', '?')
            warnings.append(f'Rate limit reached. Please wait {reset_seconds} seconds')
    return warnings


def extract_assistant_texts(item: Dict) -> List[str]:
    """conversation.item.created の item からアシスタントのテキストを抽出する.

    Args:
        item: conversation.item.created イベントの item dict。

    Returns:
        アシスタントのメッセージ (type: output_text) のテキストのリスト。
    """
    if item.get('role') != 'assistant' or item.get('type') != 'message':
        return []
    return [block.get('text', '') for block in item.get('content', []) if block.get('type') == 'output_text']
