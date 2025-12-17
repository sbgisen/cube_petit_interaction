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

import rclpy

from cube_petit_interaction_msgs.srv import GetCurrentSpeaker
from cube_petit_interaction_msgs.srv import GetUserSummary


async def memory_voice(arguments: dict) -> str:
    node = None
    try:
        if not rclpy.ok():
            rclpy.init(args=None)

        node = rclpy.create_node('memory_voice_client')

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

        speaker = future.result()
        if speaker is None or speaker.is_new or not speaker.user_id:
            return 'まだあなたのことをよく知らないみたい'

        user_id = speaker.user_id

        summary_client = node.create_client(
            GetUserSummary,
            'get_user_summary',
        )
        if not summary_client.wait_for_service(timeout_sec=1.0):
            return 'ごめんね、まだ思い出せないみたい'

        req = GetUserSummary.Request()
        req.user_id = user_id

        future = summary_client.call_async(req)
        while not future.done():
            rclpy.spin_once(node, timeout_sec=0.0)
            await asyncio.sleep(0.01)

        res = future.result()
        if res is None:
            return 'ちょっと記憶があいまいみたい'

        node.get_logger().info(f'GetUserSummary: '
                               f'user_id={user_id}, '
                               f'count={res.interaction_count}, '
                               f'conf={res.confidence:.2f}, '
                               f'has_name={res.has_name}, '
                               f'name="{res.display_name}"')

        if res.has_name:
            return f'あなたは {res.display_name} さんだよ'
        elif res.interaction_count >= 3:
            return '何度かお話ししてる人だよ'
        else:
            return 'はじめて話す人だと思う'

    except Exception as e:
        return f'Failed to handle memory_voice call: {e}'

    finally:
        if node is not None:
            node.destroy_node()
