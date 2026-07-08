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
import base64
from datetime import datetime
import importlib
import json
import queue
import sys
import threading
from typing import Optional

from audio_common_msgs.msg import AudioDataStamped
from audio_common_msgs.msg import AudioInfo
from cube_petit_chat.nodes.util.name_logic import DEFAULT_ROBOT
from cube_petit_chat.nodes.util.name_logic import speech_action_server_name
from cube_petit_chat_msgs.msg import RealtimeState
from cube_petit_chat_msgs.srv import AddContext
from cube_petit_speech_msgs.action import Speech
import numpy
from rcl_interfaces.msg import SetParametersResult
import rclpy
from rclpy.action import ActionClient
from rclpy.executors import ExternalShutdownException
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.publisher import Publisher
from rclpy.task import Future
# from sbgisen_speech_msgs.action import Speech
import sounddevice
from std_msgs.msg import String
from std_srvs.srv import SetBool
from std_srvs.srv import Trigger
import websockets
from websockets.protocol import State
import yaml


class RealtimeGPTChat(Node):
    """Node defined for having a realtime chat by ChatGPT API."""

    def __init__(self) -> None:
        """Initialize the class instance."""
        super().__init__('realtime_gpt_chat')

        self.srv = self.create_service(SetBool, 'enable_realtime_conversation', self.enable_service_callback)
        self.get_status_srv = self.create_service(Trigger, 'get_realtime_conversation_status',
                                                  self.get_status_callback)
        self.text_publisher: Publisher = self.create_publisher(String, 'realtime_conversation_content', 10)
        self.status_publisher: Publisher = self.create_publisher(RealtimeState, 'realtime_conversation_status', 10)
        self.add_context_srv = self.create_service(AddContext, 'add_realtime_context', self.add_context_callback)

        self.status_msg = RealtimeState()
        self.status_msg.can_receive_message = False
        self.status_msg.is_active = False
        self.publish_realtime_status()

        self.audio_threads = []
        self.assistant_text = ''
        self.all_tool_functions: dict[str, callable] = {}

        self.declare_parameters(namespace='',
                                parameters=[
                                    ('api_key', ''),
                                    ('model', 'gpt-4o-realtime-preview-2024-12-17'),
                                    ('past_context_file', ''),
                                    ('max_context_limit', 100),
                                    ('max_tokens', 1000),
                                    ('setting_file', ''),
                                    ('use_history', False),
                                    ('history_file', ''),
                                    ('use_past_context', False),
                                    ('use_input_topic', False),
                                    ('input_topic_name', ''),
                                    ('use_speech_action', False),
                                    ('use_tools', True),
                                    ('use_gpt_tools', True),
                                    ('tool_names', ['']),
                                    ('gpt_tool_names', ['']),
                                    ('waiting_time', 10),
                                    ('start_enable', False),
                                    ('instructions', ''),
                                    ('robot', DEFAULT_ROBOT),
                                ])

        api_key = self.get_parameter('api_key').get_parameter_value().string_value
        # model = self.get_parameter('model').get_parameter_value().string_value
        self.realtime_chat_setting_file = self.get_parameter('setting_file').get_parameter_value().string_value
        with open(self.realtime_chat_setting_file, 'r', encoding='utf-8') as f:
            self.instructions = f.read()

        instructions_param = self.get_parameter('instructions').get_parameter_value().string_value
        if instructions_param:
            self.instructions = instructions_param

        self.add_on_set_parameters_callback(self._on_parameter_change)
        self.use_input_topic = self.get_parameter('use_input_topic').get_parameter_value().bool_value
        self.use_history = self.get_parameter('use_history').get_parameter_value().bool_value
        self.history_file = self.get_parameter('history_file').get_parameter_value().string_value
        self.use_tools = self.get_parameter('use_tools').get_parameter_value().bool_value
        self.use_gpt_tools = self.get_parameter('use_gpt_tools').get_parameter_value().bool_value

        if self.use_tools:
            self.tool_names = self.get_parameter('tool_names').get_parameter_value().string_array_value
        else:
            self.tool_names = None

        if self.use_gpt_tools:
            self.gpt_tool_names = self.get_parameter('gpt_tool_names').get_parameter_value().string_array_value
        else:
            self.gpt_tool_names = None

        self.waiting_time = self.get_parameter('waiting_time').get_parameter_value().integer_value

        self.websocket_url = 'wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-12-17'
        self.headers = {'Authorization': 'Bearer ' + api_key, 'OpenAI-Beta': 'realtime=v1'}
        self._websocket_ref = None
        self._websocket_loop = None

        self.audio_send_queue = queue.Queue()
        self.audio_receive_queue = queue.Queue()

        self.sample_rate = 24000
        self.channels = 1
        self.chunk = 2400
        self.audio_data = None

        self._recording_speech: bool = False
        self._speech_pcm_buffer = bytearray()
        self.audio_stamped_publisher = self.create_publisher(AudioDataStamped, 'realtime_audio_stamped', 10)
        self.audio_info_publisher = self.create_publisher(AudioInfo, 'realtime_audio_info', 10)
        self.audio_info_msg = AudioInfo()
        self.audio_info_msg.channels = self.channels
        self.audio_info_msg.sample_rate = 24000
        self.audio_info_msg.sample_format = 'S16LE'
        self.audio_info_msg.bitrate = 24000 * 16 * 1
        self.audio_info_msg.coding_format = 'PCM'
        self.audio_data_msg = AudioDataStamped()

        self.input_mic_publisher = None
        if not self.use_input_topic:
            self.input_mic_publisher = self.create_publisher(AudioDataStamped, 'mic_audio_stamped', 10)
        self.human_voice_publisher = self.create_publisher(AudioDataStamped, 'human_voice_stamped', 10)

        self._waiting_status_timer: Optional[rclpy.timer.Timer] = None
        self._start_waiting_timer()

        self.use_speech_action = self.get_parameter('use_speech_action').get_parameter_value().bool_value

        if self.use_speech_action:
            self.get_logger().info('Use internal speech server for responding')
            robot = self.get_parameter('robot').get_parameter_value().string_value
            self.__action_client = ActionClient(self, Speech, speech_action_server_name(robot))
            self.__goal_template = Speech.Goal()
            self.__goal_template.emotion = 'happy'
            self.__goal_template.emotion_level = 2
            self.__goal_template.pitch = 100
            self.__goal_template.speed = 100
            self.__goal_template.volume = 100
            self._speech_goal_handle = None

            self.get_logger().info('Waiting for speech server...')

            if not self.__action_client.wait_for_server(timeout_sec=5.0):
                self.get_logger().error('Speech server not available after 5 seconds. Shutting down.')
                rclpy.shutdown()
                sys.exit(1)
            else:
                self.get_logger().info('Realtime conversation is ready')

        start_enable = self.get_parameter('start_enable').get_parameter_value().bool_value
        if start_enable:
            request = SetBool.Request()
            request.data = True
            response = SetBool.Response()
            self.enable_service_callback(request, response)

    def _push_instructions_to_session(self) -> None:
        ws = self._websocket_ref
        loop = getattr(self, '_websocket_loop', None)
        if ws is None or loop is None:
            return
        # 再接続することで新しいセッションに新しいinstructionsを適用する
        asyncio.run_coroutine_threadsafe(ws.close(), loop)
        self.get_logger().info('reconnecting websocket to apply new instructions')

    def _on_parameter_change(self, params: list) -> SetParametersResult:
        import os
        for param in params:
            if param.name == 'instructions':
                if param.value:
                    self.instructions = param.value
                    self.get_logger().info('instructions updated via parameter')
                    self._push_instructions_to_session()
            elif param.name == 'setting_file':
                if param.value:
                    try:
                        with open(param.value, 'r', encoding='utf-8') as f:
                            self.instructions = f.read()
                        self.get_logger().info(f'instructions reloaded from {param.value}')
                        self._push_instructions_to_session()
                    except Exception as e:
                        self.get_logger().error(f'Failed to reload instructions: {e}')
            elif param.name == 'history_file':
                if param.value:
                    path = param.value
                    if not os.path.exists(path):
                        try:
                            parent = os.path.dirname(path)
                            if parent:
                                os.makedirs(parent, exist_ok=True)
                            open(path, 'w', encoding='utf-8').close()
                            self.get_logger().info(f'Created new history file: {path}')
                        except Exception as e:
                            self.get_logger().error(f'Failed to create history file: {e}')
                    self.history_file = path
                    self.get_logger().info(f'history_file switched to {path}')
        return SetParametersResult(successful=True)

    # ----------------------------------------------------------------------------------##
    # Util functions : Waiting Timer
    # ----------------------------------------------------------------------------------##

    def _start_waiting_timer(self) -> None:
        """Start a one-shot 10-second ROS2 timer."""
        self.status_msg.can_receive_message = False
        self.publish_realtime_status()
        if self._waiting_status_timer is not None:
            self.get_logger().info('Cancelling existing context blocking timer...')
            self._waiting_status_timer.cancel()
            self._waiting_status_timer = None

        self.get_logger().info(
            f'Blocking reception of context from topics for the next {self.waiting_time} seconds...')

        self._waiting_status_timer = self.create_timer(
            self.waiting_time,
            self._waiting_timer_done_callback,
            callback_group=None,
        )

    def _waiting_timer_done_callback(self) -> None:
        """Wait timer."""
        self.get_logger().info('Context blocking period ended: topic inputs are now accepted.')
        self.status_msg.can_receive_message = True
        self.publish_realtime_status()
        # clear the timer reference
        if self._waiting_status_timer:
            self._waiting_status_timer.cancel()
            self._waiting_status_timer = None

    def _cancel_waiting_timer(self) -> None:
        if self._waiting_status_timer:
            self.get_logger().info('Cancelling context blocking timer manually.')
            self._waiting_status_timer.cancel()
            self._waiting_status_timer = None
        self.status_msg.can_receive_message = True
        self.publish_realtime_status()

    # ----------------------------------------------------------------------------------##
    # Util functions
    # ----------------------------------------------------------------------------------##

    def add_context_callback(self, request: AddContext.Request, response: AddContext.Response) -> AddContext.Response:
        """Add context callback."""
        if not self.status_msg.can_receive_message:
            response.success = False
            return response

        if not self.status_msg.is_active or self._websocket_ref is None:
            response.success = False
            return response

        if self._websocket_ref.state != State.OPEN:
            response.success = False
            return response

        try:
            asyncio.run(self._send_context(request))
            response.success = True
        except Exception as e:
            self.get_logger().error(f'Failed to add context: {e}')
            response.success = False

        return response

    async def _send_context(self, request: AddContext.Request) -> None:
        """Send ws."""
        role_map = {
            0: 'system',
            1: 'assistant',
            2: 'user',
        }
        role = role_map.get(request.role, 'user')
        if role == 'assistant':
            content_type = 'text'
        else:
            content_type = 'input_text'

        content = [{'type': content_type, 'text': request.context}]
        for img in request.images:
            img_bytes = bytes(img.data)
            b64 = base64.b64encode(img_bytes).decode()
            content.append({
                'type': 'input_image',
                'image_url': f'data:image/jpeg;base64,{b64}',
            })

        if role == 'user':
            message = {
                'type': 'response.create',
                'response': {
                    'modalities': ['text'],
                    'input': [{
                        'type': 'message',
                        'role': 'user',
                        'content': content,
                    }]
                }
            }
        else:
            message = {
                'type': 'conversation.item.create',
                'item': {
                    'type': 'message',
                    'role': role,
                    'content': content,
                }
            }

        await self._websocket_ref.send(json.dumps(message))

    def publish_realtime_status(self) -> None:
        """Comment."""
        self.status_publisher.publish(self.status_msg)

    def save_to_history(self, role: str, content: str) -> None:
        """Append role-content pair to history file."""
        if not self.use_history or not self.history_file:
            return
        try:
            with open(self.history_file, 'a', encoding='utf-8') as f:
                json.dump({
                    'timestamp': datetime.now().isoformat(timespec='seconds'),
                    'role': role,
                    'content': content
                },
                          f,
                          ensure_ascii=False)
                f.write('\n')
        except Exception as e:
            self.get_logger().warn(f'Failed to save history: {e}')

    def load_history(self) -> list:
        """Load conversation history as a list of dicts."""
        history = []
        if not self.use_history or not self.history_file:
            return history
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-15:]
                for line in lines:
                    try:
                        history.append(json.loads(line.strip()))
                    except json.JSONDecodeError:
                        continue
        except FileNotFoundError:
            self.get_logger().info(f'History file {self.history_file} not found. Starting fresh.')
        return history

    # ----------------------------------------------------------------------------------##
    # Action Server: Speech
    # ----------------------------------------------------------------------------------##

    def _on_goal_response(self, future: Future) -> bool:
        """Response when goal response is received."""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('Speech goal was rejected.')
            return
        self.get_logger().info('Speech goal accepted.')
        self._speech_goal_handle = goal_handle

        result_future = goal_handle.get_result_async()

        def _on_result_done(fut: Future) -> None:
            self.get_logger().info('Speech goal completed.')
            self._speech_goal_handle = None

        result_future.add_done_callback(_on_result_done)

    def cancel_speech(self) -> None:
        """Cancel the speech goal if active."""
        self.get_logger().info('Attempting to cancel the speech goal...')
        if self._speech_goal_handle:
            try:
                if not self._speech_goal_handle.is_done:
                    cancel_future = self._speech_goal_handle.cancel_goal_async()
                    rclpy.spin_until_future_complete(self, cancel_future, timeout_sec=1.0)
                    self.get_logger().info('Speech goal cancelled.')
            except Exception as e:
                self.get_logger().warn(f'Cancel failed: {e}')
            finally:
                self._speech_goal_handle = None
        else:
            self.get_logger().info('No active speech goal to cancel.')

    # ----------------------------------------------------------------------------------##
    # Streaming Audio Functions
    # ----------------------------------------------------------------------------------##

    def audio_callback(self, msg: AudioDataStamped) -> None:
        """Get Audio Stream from topic."""
        self.read_audio_from_topic(msg)

    def read_audio_from_topic(self, msg: AudioDataStamped) -> None:
        """Convert AudioDataStamped message and put into send queue."""
        if self.status_msg.is_active:
            try:
                self.audio_send_queue.put(bytes(msg.audio.data))
            except Exception as e:
                self.get_logger().warn(f'Failed to buffer audio from topic: {e}')

    def read_audio_to_queue(self, input_stream: sounddevice.InputStream) -> None:
        """Read audio data from the input stream and store it in the queue."""
        while self.status_msg.is_active:
            try:
                audio_data, _ = input_stream.read(self.chunk)
                pcm_bytes = audio_data.tobytes()
                self.audio_send_queue.put(pcm_bytes)

                if self.input_mic_publisher is not None:
                    msg = AudioDataStamped()
                    msg.header.stamp = self.get_clock().now().to_msg()
                    msg.header.frame_id = 'mic'
                    msg.audio.data = pcm_bytes
                    self.input_mic_publisher.publish(msg)
            except Exception as e:
                self.get_logger().info(f'Error read input stream {e}')
                break

    def play_audio_from_queue(self, output_stream: sounddevice.OutputStream) -> None:
        """Retrieve and play audio data from the queue."""
        while self.status_msg.is_active:
            try:
                pcm16_audio = self.audio_receive_queue.get(timeout=1)
                if pcm16_audio:
                    audio_array = numpy.frombuffer(pcm16_audio, dtype='int16')
                    output_stream.write(audio_array)
            except queue.Empty:
                continue
            except Exception as e:
                self.get_logger().info(f'Error writing output stream: {e}')
                break

    async def send_audio_from_queue(self, websocket: websockets.ClientConnection) -> None:
        """Send audio data from the queue to the WebSocket server."""
        while self.status_msg.is_active:
            audio_data = await asyncio.get_event_loop().run_in_executor(None, self.audio_send_queue.get)
            if audio_data is None:
                continue
            if self._recording_speech:
                self._speech_pcm_buffer.extend(audio_data)
            base64_audio = base64.b64encode(audio_data).decode('utf-8')
            audio_event = {'type': 'input_audio_buffer.append', 'audio': base64_audio}
            await websocket.send(json.dumps(audio_event))
            await asyncio.sleep(0)

    async def receive_audio_to_queue(self, websocket: websockets.ClientConnection) -> None:
        """Receive audio response from the WebSocket server and store it in the queue."""
        while self.status_msg.is_active:
            try:
                response = await websocket.recv()
            except websockets.exceptions.ConnectionClosed as e:
                self.get_logger().error(f'WebSocket connection closed: {e}')
                break
            except Exception as e:
                self.get_logger().error(f'WebSocket recv() failed: {e}')
                await asyncio.sleep(1)
                continue

            try:
                if response:

                    response_data = json.loads(response)
                    response_type = response_data.get('type')
                    self.get_logger().info(response)
                    # Display the server response in real-time
                    if response_type == 'response.function_call_arguments.done':
                        name = response_data.get('name')
                        call_id = response_data.get('call_id')
                        args = response_data.get('arguments', '{}')
                        self.get_logger().info(f'Function call: {name}({args})')
                        if 'memory' in name:
                            if self.audio_data_msg is None or len(self.audio_data_msg.audio.data) == 0:
                                self.get_logger().warn('No audio data available to publish')
                                return
                            self.audio_info_publisher.publish(self.audio_info_msg)
                            self.audio_stamped_publisher.publish(self.audio_data_msg)
                            self.get_logger().info(
                                f'Published AudioDataStamped (bytes={len(self._speech_pcm_buffer)})')
                            self._speech_pcm_buffer.clear()

                        if name in self.all_tool_functions:
                            try:
                                raw_args = response_data.get('arguments', '{}')
                                try:
                                    parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                                except json.JSONDecodeError:
                                    parsed_args = {}

                                result = await self.all_tool_functions[name](parsed_args)

                                tool_event = {
                                    'type': 'conversation.item.create',
                                    'item': {
                                        'type': 'function_call_output',
                                        'call_id': call_id,
                                        'output': json.dumps({'result': result}, ensure_ascii=False)
                                    }
                                }

                                await websocket.send(json.dumps(tool_event))

                                # Ask the model to continue after tool execution
                                await websocket.send(
                                    json.dumps({
                                        'type': 'response.create',
                                        'response': {
                                            'modalities': ['text']
                                        }
                                    }))

                            except Exception as e:
                                self.get_logger().error(f'Error executing tool "{name}": {e}')

                        # if hasattr(self, 'tool_functions') and name in self.tool_functions:
                        #     try:
                        #         raw_args = response_data.get('arguments', '{}')
                        #         parsed_args = {}
                        #         try:
                        #             parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        #         except json.JSONDecodeError:
                        #             parsed_args = {}

                        #         result = await self.tool_functions[name](parsed_args)
                        #         tool_output = json.dumps({'result': result}, ensure_ascii=False)

                        #         tool_event = {
                        #             'type': 'conversation.item.create',
                        #             'item': {
                        #                 'type': 'function_call_output',
                        #                 'call_id': call_id,
                        #                 'output': tool_output
                        #             }
                        #         }
                        #         await websocket.send(json.dumps(tool_event))
                        #         await websocket.send(
                        #             json.dumps({
                        #                 'type': 'response.create',
                        #                 'response': {
                        #                     'modalities': ['text']
                        #                 }
                        #             }))
                        #     except Exception as e:
                        #         self.get_logger().error(f'Error executing tool {name}: {e}')

                        # if hasattr(self, 'tool_functions') and name in self.gpt_tool_functions:
                        #     try:
                        #         raw_args = response_data.get('arguments', '{}')
                        #         parsed_args = {}
                        #         try:
                        #             parsed_args = json.loads(raw_args) if isinstance(raw_args, str) else raw_args
                        #         except json.JSONDecodeError:
                        #             parsed_args = {}

                        #         result = await self.gpt_tool_functions[name](parsed_args)
                        #         tool_output = json.dumps({'result': result}, ensure_ascii=False)

                        #         tool_event = {
                        #             'type': 'conversation.item.create',
                        #             'item': {
                        #                 'type': 'function_call_output',
                        #                 'call_id': call_id,
                        #                 'output': tool_output
                        #             }
                        #         }
                        #         await websocket.send(json.dumps(tool_event))
                        #         await websocket.send(
                        #             json.dumps({
                        #                 'type': 'response.create',
                        #                 'response': {
                        #                     'modalities': ['text']
                        #                 }
                        #             }))
                        #     except Exception as e:
                        #         self.get_logger().error(f'Error executing tool {name}: {e}')
                        #     continue

                    if response_type == 'conversation.item.created':
                        item = response_data.get('item', {})
                        if item.get('role') == 'assistant' and item.get('type') == 'message':
                            contents = item.get('content', [])
                            for content_block in contents:
                                if content_block.get('type') == 'text':
                                    message = content_block.get('text', '')
                                    text_msg = String()
                                    text_msg.data = f'assistant: {message}'
                                    self.text_publisher.publish(text_msg)
                                    self.save_to_history('assistant', message)
                                    if self.__action_client.wait_for_server(timeout_sec=5.0):
                                        self.__goal_template.text = message
                                        if self._speech_goal_handle and not self._speech_goal_handle.is_done:
                                            try:
                                                cancel_future = self._speech_goal_handle.cancel_goal_async()
                                                rclpy.spin_until_future_complete(self, cancel_future, timeout_sec=1.0)
                                                self.get_logger().info('Sent cancel request for previous speech goal.')

                                                if cancel_future.result() and hasattr(
                                                        cancel_future.result(), 'return_code'):
                                                    if cancel_future.result(
                                                    ).return_code == 0:  # 0 = CANCEL_GOAL_ACCEPTED
                                                        result_future = self._speech_goal_handle.get_result_async()
                                                        self.get_logger().info(
                                                            'Waiting for goal to actually cancel...')
                                                        rclpy.spin_until_future_complete(self,
                                                                                         result_future,
                                                                                         timeout_sec=2.0)
                                                        self.get_logger().info('Previous speech goal fully cancelled.')
                                            except Exception as e:
                                                self.get_logger().warn(f'Failed to cancel previous speech goal: {e}')
                                        self.__goal_template.text = message if 'message' in locals(
                                        ) else self.assistant_text
                                        self.get_logger().info(self.__goal_template.text)
                                        future = self.__action_client.send_goal_async(self.__goal_template)
                                        future.add_done_callback(self._on_goal_response)
                                    else:
                                        self.get_logger().error('Speech action server not available.')
                    if response_type in ('response.audio_transcript.delta', 'response.text.delta'):
                        self.assistant_text += response_data['delta']
                    # Retrieve the completion status of the server response
                    elif response_type in ('response.audio_transcript.done', 'response.text.done'):

                        text_msg = String()
                        text_msg.data = f'robot: {self.assistant_text}'
                        self.text_publisher.publish(text_msg)
                        self.save_to_history('assistant', self.assistant_text)
                        if response_type == 'response.text.done':
                            if self.__action_client.wait_for_server(timeout_sec=5.0):
                                self.__goal_template.text = self.assistant_text
                                if self._speech_goal_handle and not self._speech_goal_handle.is_done:
                                    try:
                                        cancel_future = self._speech_goal_handle.cancel_goal_async()
                                        rclpy.spin_until_future_complete(self, cancel_future, timeout_sec=1.0)
                                        self.get_logger().info('Sent cancel request for previous speech goal.')

                                        if cancel_future.result() and hasattr(cancel_future.result(), 'return_code'):
                                            if cancel_future.result().return_code == 0:  # 0 = CANCEL_GOAL_ACCEPTED
                                                result_future = self._speech_goal_handle.get_result_async()
                                                self.get_logger().info('Waiting for goal to actually cancel...')
                                                rclpy.spin_until_future_complete(self, result_future, timeout_sec=2.0)
                                                self.get_logger().info('Previous speech goal fully cancelled.')
                                    except Exception as e:
                                        self.get_logger().warn(f'Failed to cancel previous speech goal: {e}')
                                self.__goal_template.text = message if 'message' in locals() else self.assistant_text
                                self.get_logger().info(self.__goal_template.text)

                                future = self.__action_client.send_goal_async(self.__goal_template)
                                future.add_done_callback(self._on_goal_response)
                            else:
                                self.get_logger().error('Speech action server not available.')
                        self.assistant_text = ''
                        self._start_waiting_timer()
                    # Output the transcription of the user's speech
                    elif response_type == 'conversation.item.input_audio_transcription.completed':
                        transcript = response_data.get('transcript', '').replace('\n', '')
                        text_msg = String()
                        text_msg.data = f'user: {transcript}'
                        self.text_publisher.publish(text_msg)
                        self.save_to_history('user', transcript)
                        if '私は誰' in transcript:
                            if self.audio_data_msg is None or len(self.audio_data_msg.audio.data) == 0:
                                self.get_logger().warn('No audio data available to publish')
                                return
                            self.audio_info_publisher.publish(self.audio_info_msg)
                            self.audio_stamped_publisher.publish(self.audio_data_msg)
                            self.get_logger().info(
                                f'Published AudioDataStamped (bytes={len(self._speech_pcm_buffer)})')
                            self._speech_pcm_buffer.clear()
                    # Retrieve rate limit information
                    elif response_type == 'rate_limits.updated':
                        rate_limits = response_data.get('rate_limits', [])
                        if len(rate_limits) >= 2:
                            remaining_requests = rate_limits[0].get('remaining', 1)
                            remaining_tokens = rate_limits[1].get('remaining', 1)
                            if remaining_requests == 0:
                                reset_seconds = rate_limits[0].get('reset_seconds', '?')
                                self.get_logger().warn(f'Rate limit reached. Please wait {reset_seconds} seconds')
                            if remaining_tokens == 0:
                                reset_seconds = rate_limits[1].get('reset_seconds', '?')
                                self.get_logger().warn(f'Rate limit reached. Please wait {reset_seconds} seconds')
                    # Confirm that the server has recognized the start of this utterance
                    if 'type' in response_data and response_data['type'] == 'input_audio_buffer.speech_started':
                        self._cancel_waiting_timer()
                        self.cancel_speech()
                        self.get_logger().info('Speech started: begin recording audio')
                        self._recording_speech = True
                        self._speech_pcm_buffer.clear()
                        while not self.audio_receive_queue.empty():
                            self.audio_receive_queue.get()
                    if response_data['type'] == 'input_audio_buffer.speech_stopped':
                        self.get_logger().info('Speech stopped: publish AudioDataStamped')
                        self._recording_speech = False
                        if len(self._speech_pcm_buffer) == 0:
                            self.get_logger().warn('No audio captured for this utterance')
                            return
                        human_msg = AudioDataStamped()
                        human_msg.header.stamp = self.get_clock().now().to_msg()
                        human_msg.header.frame_id = 'mic'
                        human_msg.audio.data = bytes(self._speech_pcm_buffer)
                        self.human_voice_publisher.publish(human_msg)
                        self.get_logger().info(f'Published human_voice_stamped (bytes={len(self._speech_pcm_buffer)})')

                        self.audio_data_msg.header.stamp = self.get_clock().now().to_msg()
                        self.audio_data_msg.header.frame_id = 'mic'
                        self.audio_data_msg.audio.data = bytes(self._speech_pcm_buffer)
                    if 'type' in response_data and response_data['type'] == 'response.audio.delta':
                        base64_audio_response = response_data['delta']
                        if base64_audio_response:
                            pcm16_audio = base64.b64decode(base64_audio_response)
                            self.audio_receive_queue.put(pcm16_audio)
            except Exception as e:
                self.get_logger().error(f'Error processing websocket message: {e}')
                continue

            await asyncio.sleep(0)

    async def stream_audio_and_receive_response(self) -> None:
        """Establish a WebSocket connection and manage audio streaming."""
        # if self.use_topic is true, add tools from yaml and python data
        # tools_file_path = '/config/realtime_tools_' + self.tool_names[0] + '.yaml'
        # python_file_path = '/config/realtime_tools_' + self.tool_names[0] + '.py'
        # function_name = self.tool_names[0]

        while self.status_msg.is_active:
            try:
                async with websockets.connect(self.websocket_url, additional_headers=self.headers) as websocket:
                    self._websocket_ref = websocket
                    update_request = {
                        'type': 'session.update',
                        'session': {
                            'modalities': ['text'] if self.use_speech_action else ['audio', 'text'],
                            'instructions': self.instructions,
                            'voice': 'alloy',
                            'turn_detection': {
                                'type': 'server_vad',
                                'threshold': 0.5,
                            },
                            'input_audio_transcription': {
                                'model': 'whisper-1'
                            }
                        }
                    }

                    if self.use_history:
                        history = self.load_history()
                        history_text = '\n'.join([f"{item['role']}: {item['content']}" for item in history])
                        update_request['session']['instructions'] = history_text + '\n' + self.instructions

                    self.get_logger().info(str(self.use_tools))
                    self.get_logger().info(str(self.tool_names))
                    tools_yaml = []
                    self.tool_functions = {}
                    if self.use_tools and self.tool_names:

                        for tool_name in self.tool_names:
                            try:
                                yaml_path = self.declare_parameter(f'tools.{tool_name}.yaml_path',
                                                                   '').get_parameter_value().string_value

                                py_path = self.declare_parameter(f'tools.{tool_name}.python_path',
                                                                 '').get_parameter_value().string_value

                                self.get_logger().info(f'Looking for tool in: {yaml_path}')
                                self.get_logger().info(f'Looking for python in: {py_path}')

                                with open(yaml_path, 'r', encoding='utf-8') as f:
                                    tool_yaml = yaml.safe_load(f)

                                tools_yaml.append(tool_yaml)
                                self.get_logger().info(f"YAML loaded successfully: {tool_yaml.get('name')}")

                                spec = importlib.util.spec_from_file_location(tool_name, py_path)
                                module = importlib.util.module_from_spec(spec)
                                spec.loader.exec_module(module)

                                self.tool_functions[tool_name] = getattr(module, tool_name)
                                self.get_logger().info(f'Loaded tool: {tool_name}')
                                self.all_tool_functions[tool_name] = getattr(module, tool_name)

                            except Exception as e:
                                self.get_logger().error(f'Failed to load tool {tool_name}: {e}')

                    self.get_logger().info(str(self.use_gpt_tools))
                    self.get_logger().info(str(self.gpt_tool_names))
                    gpt_tools_yaml = []
                    self.gpt_tool_functions = {}
                    if self.use_gpt_tools and self.gpt_tool_names:
                        for tool_name in self.gpt_tool_names:
                            try:
                                yaml_path = self.declare_parameter(f'gpt_tools.{tool_name}.yaml_path',
                                                                   '').get_parameter_value().string_value

                                py_path = self.declare_parameter(f'gpt_tools.{tool_name}.python_path',
                                                                 '').get_parameter_value().string_value

                                self.get_logger().info(f'Looking for gpt_tool in: {yaml_path}')
                                self.get_logger().info(f'Looking for python in: {py_path}')

                                with open(yaml_path, 'r', encoding='utf-8') as f:
                                    tool_yaml = yaml.safe_load(f)

                                gpt_tools_yaml.append(tool_yaml)
                                self.get_logger().info(f"YAML loaded successfully: {tool_yaml.get('name')}")

                                spec = importlib.util.spec_from_file_location(tool_name, py_path)
                                module = importlib.util.module_from_spec(spec)
                                spec.loader.exec_module(module)

                                self.gpt_tool_functions[tool_name] = getattr(module, tool_name)
                                self.get_logger().info(f'Loaded tool: {tool_name}')
                                self.all_tool_functions[tool_name] = getattr(module, tool_name)

                            except Exception as e:
                                self.get_logger().error(f'Failed to load tool {tool_name}: {e}')

                    all_tools = []
                    if self.use_tools and self.tool_names:
                        all_tools.extend(tools_yaml)

                    if self.use_gpt_tools and self.gpt_tool_names:
                        all_tools.extend(gpt_tools_yaml)

                    if all_tools:
                        update_request['session']['tools'] = all_tools

                    await websocket.send(json.dumps(update_request))

                    send_task = asyncio.create_task(self.send_audio_from_queue(websocket))
                    receive_task = asyncio.create_task(self.receive_audio_to_queue(websocket))

                    pending = await asyncio.wait([send_task, receive_task], return_when=asyncio.FIRST_EXCEPTION)
                    for task in pending:
                        if not task.done():
                            task.cancel()

            except websockets.exceptions.ConnectionClosedOK:
                self.get_logger().warn('WebSocket connection closed normally (1000 OK). Reconnecting...')
            except Exception as e:
                self.get_logger().error(f'WebSocket connection error: {e}')

            if self.status_msg.is_active:
                self.get_logger().info('Reconnecting to WebSocket in 2 seconds...')
                await asyncio.sleep(2)

    def enable_service_callback(self, request: SetBool.Request, response: SetBool.Response) -> SetBool.Response:
        """Handle service requests to start/stop audio streaming."""
        if request.data:
            if self.status_msg.is_active:
                self.get_logger().warning('Audio streaming is already running, ignoring request.')
                response.success = True
            else:
                self.start_audio_streaming()
                response.success = True
        else:
            if self.status_msg.is_active:
                self.get_logger().info('Stop audio streaming...')
                self.cancel_audio_streaming()
                response.success = True
            else:
                self.get_logger().warning('Audio streaming is already stopped, ignoring request.')
                response.success = True
        return response

    def get_status_callback(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        """Republish current status so subscribers can receive the latest state."""
        self.status_publisher.publish(self.status_msg)
        response.success = True
        response.message = ''
        return response

    def start_audio_streaming(self) -> None:
        """Execute when an audio streaming action is started."""
        self.status_msg.is_active = True
        self.get_logger().info('Start audio streaming...')

        # Audio stream from the microphone
        if not self.use_input_topic:
            self.input_stream = sounddevice.InputStream(samplerate=self.sample_rate,
                                                        channels=self.channels,
                                                        dtype='int16',
                                                        blocksize=self.chunk)
            self.input_stream.start()
            self.audio_threads.append(
                threading.Thread(target=self.read_audio_to_queue, args=(self.input_stream,), daemon=True))
        else:
            self.audio_subscription = self.create_subscription(AudioDataStamped, 'audio_stamped', self.audio_callback,
                                                               10)
        # Audio stream received from the API
        if self.use_speech_action:
            self.output_stream = sounddevice.OutputStream(samplerate=self.sample_rate,
                                                          channels=self.channels,
                                                          dtype='int16',
                                                          blocksize=self.chunk)
            self.output_stream.start()
            self.audio_threads.append(
                threading.Thread(target=self.play_audio_from_queue, args=(self.output_stream,), daemon=True))

        # Start audio playback
        for thread in self.audio_threads:
            thread.start()

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)

        def run_asyncio_loop() -> None:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            self._websocket_loop = loop
            task = loop.create_task(self.stream_audio_and_receive_response())
            try:
                loop.run_until_complete(task)
            except asyncio.CancelledError:
                self.get_logger().info('Asyncio loop canceled')
            finally:
                self._websocket_loop = None
                loop.stop()

        self.websocket_thread = threading.Thread(target=run_asyncio_loop, daemon=True)
        self.websocket_thread.start()
        self.publish_realtime_status()

    def cancel_audio_streaming(self) -> None:
        """Stop all audio streaming and cleanup resources."""
        self.status_msg.is_active = False
        try:
            if rclpy.ok():
                self.publish_realtime_status()
            else:
                self.get_logger().warn('Context invalid; skipping status publish.')
        except Exception as e:
            self.get_logger().error(f'Failed to publish status: {e}')

        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                loop.call_soon_threadsafe(loop.stop)
        except RuntimeError:
            self.get_logger().warn('No event loop in this thread')

        if hasattr(self, 'websocket_thread') and self.websocket_thread.is_alive():
            self.websocket_thread.join(timeout=5.0)
            if self.websocket_thread.is_alive():
                self.get_logger().warn('WebSocket thread did not stop in time.')

        for thread in self.audio_threads:
            thread.join(timeout=5.0)
            if thread.is_alive():
                self.get_logger().warn('Audio thread did not stop in time.')
        self.audio_threads.clear()

        if self.use_speech_action:
            self.output_stream.close()
        if not self.use_input_topic:
            self.input_stream.close()
        elif self.audio_subscription is not None:
            self.destroy_subscription(self.audio_subscription)
            self.audio_subscription = None

    def destroy_node(self) -> None:
        """Clean up resources and stop the node."""
        self.cancel_audio_streaming()
        super().destroy_node()


def main() -> None:
    """Run node."""
    rclpy.init()
    try:
        node = RealtimeGPTChat()
        executor = MultiThreadedExecutor()
        executor.add_node(node)
        executor.spin()
    except KeyboardInterrupt:
        pass
    except ExternalShutdownException:
        sys.exit(1)
    finally:
        rclpy.try_shutdown()
        node.destroy_node()


if __name__ == '__main__':
    main()
