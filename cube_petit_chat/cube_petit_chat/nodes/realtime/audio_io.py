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
"""sounddevice による音声入出力 (ROS 非依存).

マイク入力を送信キューへ流すポンプと、受信キューをスピーカへ流すポンプを提供する。
ROS への反映 (トピック配信など) はコールバック経由で呼び出し元が行う。
"""

import queue
from typing import Callable, Optional

import numpy
import sounddevice

from cube_petit_chat.nodes.realtime import LoggerLike


def open_input_stream(sample_rate: int, channels: int, chunk: int) -> sounddevice.InputStream:
    """マイク入力ストリームを生成する (start は呼び出し元)."""
    return sounddevice.InputStream(samplerate=sample_rate, channels=channels, dtype='int16', blocksize=chunk)


def open_output_stream(sample_rate: int, channels: int, chunk: int) -> sounddevice.OutputStream:
    """スピーカ出力ストリームを生成する (start は呼び出し元)."""
    return sounddevice.OutputStream(samplerate=sample_rate, channels=channels, dtype='int16', blocksize=chunk)


def pump_input_to_queue(input_stream: sounddevice.InputStream, chunk: int, send_queue: queue.Queue,
                        is_active: Callable[[], bool], on_chunk: Optional[Callable[[bytes],
                                                                                   None]], logger: LoggerLike) -> None:
    """Read audio data from the input stream and store it in the queue.

    Args:
        input_stream: 読み取り元の入力ストリーム。
        chunk: 1 回に読み取るフレーム数。
        send_queue: PCM バイト列を積むキュー。
        is_active: 継続すべき間 True を返すコールバック。
        on_chunk: 読み取った PCM バイト列を受け取るコールバック (省略可)。
        logger: info を持つロガー。
    """
    while is_active():
        try:
            audio_data, _ = input_stream.read(chunk)
            pcm_bytes = audio_data.tobytes()
            send_queue.put(pcm_bytes)

            if on_chunk is not None:
                on_chunk(pcm_bytes)
        except Exception as e:
            logger.info(f'Error read input stream {e}')
            break


def pump_queue_to_output(output_stream: sounddevice.OutputStream, receive_queue: queue.Queue,
                         is_active: Callable[[], bool], logger: LoggerLike) -> None:
    """Retrieve and play audio data from the queue.

    Args:
        output_stream: 書き込み先の出力ストリーム。
        receive_queue: PCM バイト列を取り出すキュー。
        is_active: 継続すべき間 True を返すコールバック。
        logger: info を持つロガー。
    """
    while is_active():
        try:
            pcm16_audio = receive_queue.get(timeout=1)
            if pcm16_audio:
                audio_array = numpy.frombuffer(pcm16_audio, dtype='int16')
                output_stream.write(audio_array)
        except queue.Empty:
            continue
        except Exception as e:
            logger.info(f'Error writing output stream: {e}')
            break
