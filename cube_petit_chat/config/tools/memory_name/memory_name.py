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
import asyncio
import json

import rclpy

from cube_petit_interaction_msgs.srv import GetCurrentSpeaker
from cube_petit_interaction_msgs.srv import SetDisplayName


async def memory_name(arguments: dict) -> str:
    node = None
    try:
        if isinstance(arguments, str):
            arguments = json.loads(arguments)

        display_name = arguments.get('display_name', '').strip()

        if not display_name:
            return '名前が聞き取れなかったみたい'

        if not rclpy.ok():
            rclpy.init(args=None)

        node = rclpy.create_node('set_display_name_client')

        # --- 現在の話者取得 ---
        speaker_client = node.create_client(
            GetCurrentSpeaker,
            'get_current_speaker',
        )
        if not speaker_client.wait_for_service(timeout_sec=1.0):
            return '今は誰かわからないみたい'

        future = speaker_client.call_async(GetCurrentSpeaker.Request())
        while not future.done():
            rclpy.spin_once(node, timeout_sec=0.0)
            await asyncio.sleep(0.01)

        speaker_res = future.result()
        if speaker_res is None or speaker_res.is_new:
            return 'もう一度話しかけてくれる？'

        user_id = speaker_res.user_id

        set_client = node.create_client(
            SetDisplayName,
            'set_display_name',
        )
        if not set_client.wait_for_service(timeout_sec=1.0):
            return '名前を覚える準備ができてないみたい'

        node.get_logger().info('4------------------------------')

        req = SetDisplayName.Request()
        req.user_id = user_id
        req.display_name = display_name

        future = set_client.call_async(req)
        while not future.done():
            rclpy.spin_once(node, timeout_sec=0.0)
            await asyncio.sleep(0.01)

        node.get_logger().info('5------------------------------')

        res = future.result()
        if res and res.success:
            return f'{display_name} さんだね、覚えたよ'
        else:
            return 'うまく覚えられなかったみたい'

    except Exception as e:
        return f'名前を覚えるときにエラーが出たよ: {e}'

    finally:
        if node is not None:
            node.destroy_node()
