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

import json

import rclpy
from sbgisen_conversation_commander import ConversationCommander


async def call_gpt_api(command: str) -> str:
    """
    Call GPT chat service via ConversationCommander.

    Parameters
    ----------
    command : str
        JSON string or dict containing the chat command.

    Returns:
    -------
    str
        Chat response text.
    """
    set_namespace = 'gpt_chat'
    node = None

    try:
        if isinstance(command, str):
            command = json.loads(command)

        input_text = command.get('command', '').strip()
        if not rclpy.ok():
            rclpy.init(args=None)
        node = rclpy.create_node('call_gpt_chat')

        service_names = ['clear_chat_history', 'add_chat_context', 'chat']

        for service_name in service_names:
            full_service_name = f'{set_namespace}/{service_name}'
            if not node.wait_for_service(full_service_name, timeout_sec=5.0):
                node.get_logger().error('Chat commander service timeout')
                return 'Service timeout occurred while waiting for GPT services.'

        try:
            node._talk_conversation = ConversationCommander(node, True, f'{set_namespace}/clear_chat_history',
                                                            f'{set_namespace}/add_chat_context',
                                                            f'{set_namespace}/chat')
        except Exception:
            return 'GPT API node is not running.'

        try:
            resp = node.__talk_conversation.chat(text=input_text)
            try:
                resp_data = json.loads(resp)
                if 'speech_phrases' in resp_data:
                    text_resp = resp_data['speech_phrases']
            except json.JSONDecodeError:
                node.get_logger().warn(f'Response is not JSON. Raw content:\n{resp}')
                text_resp = resp.replace('\n', '').replace(' ', '').replace('\t', '').replace('*', '')

            node.get_logger().info(f'Use conversation_chat Return: {text_resp}')
            return text_resp
        except Exception as e:
            return f'Error occurred while calling GPT API: {e}'

    except Exception as e:
        return f'Unexpected error occurred: {e}'

    finally:
        if node is not None:
            node.destroy_node()


async def gpt_chat(arguments: dict) -> str:
    try:
        args = json.loads(arguments)
        command = args.get('command', '')
        result_text = await call_gpt_api(command)
        return f'{result_text}'

    except Exception as e:
        return f'Failed to handle chat gpt api call: {e}'
