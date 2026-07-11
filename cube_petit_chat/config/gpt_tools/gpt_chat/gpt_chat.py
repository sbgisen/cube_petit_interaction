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
#
"""gpt_chat tool: forward a query to the gpt_api_chat node via its Chat service."""

import asyncio
import json

import rclpy

from cube_petit_chat_msgs.srv import Chat


def call_gpt_api(command: str) -> str:
    """Call the gpt_api_chat node's Chat service (blocking; run in a worker thread).

    Parameters
    ----------
    command : str
        Text to send to the GPT chat service.

    Returns:
    -------
    str
        Chat response text (or an error message on failure).
    """
    node = None
    try:
        if not rclpy.ok():
            rclpy.init(args=None)
        # use_global_arguments=False: this tool runs inside the realtime node's process,
        # whose global --ros-args (-r __ns:=<robot>, -r __node:=realtime_gpt_chat) would
        # otherwise rename this throwaway node and re-namespace relative service names.
        node = rclpy.create_node('call_gpt_chat', use_global_arguments=False)

        # Absolute name: the per-tool gpt_api_chat nodes are spawned at the root namespace
        # by cube_petit_realtime_chat.launch.py regardless of the robot namespace.
        chat_client = node.create_client(Chat, '/gpt_chat/chat')
        # 15s covers the gpt_api_chat node's startup (uv + venv boot takes >5s), so the
        # first tool call fired right after launch doesn't race the service into a timeout.
        if not chat_client.wait_for_service(timeout_sec=15.0):
            node.get_logger().error('gpt_chat/chat service timeout')
            return '頭の準備がまだ終わっていないみたい。少し待ってからもう一度聞いてほしい、と伝えてください。'

        request = Chat.Request()
        request.text = command
        future = chat_client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=60.0)
        if not future.done():
            node.get_logger().error('gpt_chat/chat did not respond in time')
            return 'GPT chat service did not respond in time.'

        response = future.result()
        text_resp = response.response.replace('\n', '').replace('*', '')
        node.get_logger().info(f'gpt_chat service returned: {text_resp}')
        return text_resp or 'No response was returned from the GPT chat service.'

    except Exception as e:
        return f'Error occurred while calling GPT API: {e}'

    finally:
        if node is not None:
            node.destroy_node()


async def gpt_chat(arguments: dict) -> str:
    """Entry point called by the realtime node when the gpt_chat function is invoked.

    Parameters
    ----------
    arguments : dict
        Function-call arguments from the realtime API ({'command': str}).

    Returns:
    -------
    str
        Chat response text to feed back to the realtime session.
    """
    try:
        args = {}

        if isinstance(arguments, str):
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                args = {}
        elif isinstance(arguments, dict):
            args = arguments

        command = args.get('command', '')
        # Run the blocking service call in a worker thread so the realtime
        # websocket loop keeps receiving events while GPT is thinking.
        loop = asyncio.get_running_loop()
        result_text = await loop.run_in_executor(None, call_gpt_api, command)
        return f'{result_text}'

    except Exception as e:
        return f'Failed to handle chat gpt api call: {e}'
