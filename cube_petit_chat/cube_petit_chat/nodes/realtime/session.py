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
"""OpenAI Realtime API の WebSocket セッション管理 (ROS 非依存).

接続・再接続ループ、音声送信タスク、イベント受信タスクを担う。
ROS への反映はコールバック (on_event / on_audio_chunk) 経由で呼び出し元が行う。
"""

import asyncio
import json
import queue
from typing import Awaitable, Callable, Dict, Optional

import websockets

from cube_petit_chat.nodes.realtime import LoggerLike
from cube_petit_chat.nodes.realtime.protocol import encode_audio_append_event


class RealtimeSession:
    """WebSocket 接続と送受信タスクを管理するクラス.

    Attributes:
        url: 接続先の WebSocket URL。
        headers: 接続時に付与する HTTP ヘッダ。
    """

    def __init__(self,
                 url: str,
                 headers: Dict[str, str],
                 send_queue: queue.Queue,
                 is_active: Callable[[], bool],
                 build_session_config: Callable[[], Dict],
                 on_event: Callable[[Dict, websockets.ClientConnection], Awaitable[Optional[bool]]],
                 logger: LoggerLike,
                 on_connect: Optional[Callable[[websockets.ClientConnection], None]] = None,
                 on_audio_chunk: Optional[Callable[[bytes], None]] = None) -> None:
        """Initialize the session.

        Args:
            url: 接続先の WebSocket URL。
            headers: 接続時に付与する HTTP ヘッダ。
            send_queue: 送信する PCM バイト列を取り出すキュー。
            is_active: セッションを継続すべき間 True を返すコールバック。
            build_session_config: 接続ごとに session.update イベント dict を組み立てるコールバック。
            on_event: 受信イベントを処理する async コールバック。True を返すと受信ループを終了する。
            logger: info/warn/error を持つロガー (rclpy の Logger 等)。
            on_connect: 接続確立時に WebSocket を受け取るコールバック (省略可)。
            on_audio_chunk: 送信直前の PCM バイト列を受け取るコールバック (省略可)。
        """
        self.url = url
        self.headers = headers
        self._send_queue = send_queue
        self._is_active = is_active
        self._build_session_config = build_session_config
        self._on_event = on_event
        self._logger = logger
        self._on_connect = on_connect
        self._on_audio_chunk = on_audio_chunk

    async def run(self) -> None:
        """Establish a WebSocket connection and manage audio streaming."""
        while self._is_active():
            try:
                async with websockets.connect(self.url, additional_headers=self.headers) as websocket:
                    if self._on_connect is not None:
                        self._on_connect(websocket)

                    update_request = self._build_session_config()
                    await websocket.send(json.dumps(update_request))

                    send_task = asyncio.create_task(self.send_audio_from_queue(websocket))
                    receive_task = asyncio.create_task(self.receive_events(websocket))

                    pending = await asyncio.wait([send_task, receive_task], return_when=asyncio.FIRST_EXCEPTION)
                    for task in pending:
                        if not task.done():
                            task.cancel()

            except websockets.exceptions.ConnectionClosedOK:
                self._logger.warn('WebSocket connection closed normally (1000 OK). Reconnecting...')
            except Exception as e:
                self._logger.error(f'WebSocket connection error: {e}')

            if self._is_active():
                self._logger.info('Reconnecting to WebSocket in 2 seconds...')
                await asyncio.sleep(2)

    async def send_audio_from_queue(self, websocket: websockets.ClientConnection) -> None:
        """Send audio data from the queue to the WebSocket server."""
        while self._is_active():
            audio_data = await asyncio.get_event_loop().run_in_executor(None, self._send_queue.get)
            if audio_data is None:
                continue
            if self._on_audio_chunk is not None:
                self._on_audio_chunk(audio_data)
            await websocket.send(json.dumps(encode_audio_append_event(audio_data)))
            await asyncio.sleep(0)

    async def receive_events(self, websocket: websockets.ClientConnection) -> None:
        """Receive server events from the WebSocket and dispatch them to on_event."""
        while self._is_active():
            try:
                response = await websocket.recv()
            except websockets.exceptions.ConnectionClosed as e:
                self._logger.error(f'WebSocket connection closed: {e}')
                break
            except Exception as e:
                self._logger.error(f'WebSocket recv() failed: {e}')
                await asyncio.sleep(1)
                continue

            try:
                if response:
                    response_data = json.loads(response)
                    self._logger.info(response)
                    stop = await self._on_event(response_data, websocket)
                    if stop:
                        return
            except Exception as e:
                self._logger.error(f'Error processing websocket message: {e}')
                continue

            await asyncio.sleep(0)
