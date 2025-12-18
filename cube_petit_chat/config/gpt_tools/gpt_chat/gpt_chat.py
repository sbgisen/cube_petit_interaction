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
from sbgisen_conversation_commander import ConversationCommander
from sbgisen_conversation_msgs.srv import Chat


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
        input_text = command
        if not rclpy.ok():
            rclpy.init(args=None)
        node = rclpy.create_node('call_gpt_chat')

        # service_names = ['clear_chat_history', 'add_chat_context', 'chat']
        # service_type = [Trigger, AddContext, Chat]
        chat_client = node.create_client(Chat, set_namespace + '/chat')
        if not chat_client.wait_for_service(timeout_sec=5.0):
            node.get_logger().error('Chat commander service timeout')
            return 'Service timeout occurred while waiting for GPT services.'
        # for service_name in service_names:
        #     client = node.create_client(SomeSrvType, full_service_name)
        #     if not client.wait_for_service(full_service_name, timeout_sec=5.0):
        #         node.get_logger().error('Chat commander service timeout')
        #         return 'Service timeout occurred while waiting for GPT services.'

        try:
            talk_conversation = ConversationCommander(node, True, f'{set_namespace}/clear_chat_history',
                                                      f'{set_namespace}/add_chat_context', f'{set_namespace}/chat')
        except Exception:
            return 'GPT API node is not running.'

        try:
            node.get_logger().info('Before chat()')
            loop = asyncio.get_running_loop()
            resp = await loop.run_in_executor(None, lambda: talk_conversation.chat(text=input_text))
            node.get_logger().info('After chat()')

            for _ in range(50):
                rclpy.spin_once(node, timeout_sec=0.0)
                await asyncio.sleep(0.01)
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
        args = {}

        if isinstance(arguments, str):
            try:
                args = json.loads(arguments)
            except json.JSONDecodeError:
                args = {}
        elif isinstance(arguments, dict):
            args = arguments

        command = args.get('command', '')
        result_text = await call_gpt_api(command)
        return f'{result_text}'

    except Exception as e:
        return f'Failed to handle chat gpt api call: {e}'
