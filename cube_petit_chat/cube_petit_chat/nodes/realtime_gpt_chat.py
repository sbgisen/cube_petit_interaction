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
from datetime import datetime
import json
import queue
import sys
import threading
from typing import Optional

from action_msgs.msg import GoalStatus
from audio_common_msgs.msg import AudioDataStamped
from audio_common_msgs.msg import AudioInfo
from cube_petit_chat_msgs.msg import RealtimeState
from cube_petit_speech_msgs.action import Speech
from rcl_interfaces.msg import SetParametersResult
import rclpy
from rclpy.action import ActionClient
from rclpy.action.client import ClientGoalHandle
from rclpy.executors import ExternalShutdownException
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.publisher import Publisher
from rclpy.task import Future
# from sbgisen_speech_msgs.action import Speech
from std_msgs.msg import String
from std_srvs.srv import SetBool
from std_srvs.srv import Trigger
import websockets
from websockets.protocol import State

from cube_petit_chat.nodes.realtime import audio_io
from cube_petit_chat.nodes.realtime import tools as realtime_tools
from cube_petit_chat.nodes.realtime.protocol import build_context_message
from cube_petit_chat.nodes.realtime.protocol import build_session_update
from cube_petit_chat.nodes.realtime.protocol import build_tool_result_events
from cube_petit_chat.nodes.realtime.protocol import build_websocket_headers
from cube_petit_chat.nodes.realtime.protocol import build_websocket_url
from cube_petit_chat.nodes.realtime.protocol import decode_audio_delta
from cube_petit_chat.nodes.realtime.protocol import DEFAULT_REALTIME_MODEL
from cube_petit_chat.nodes.realtime.protocol import extract_assistant_texts
from cube_petit_chat.nodes.realtime.protocol import merge_history_into_instructions
from cube_petit_chat.nodes.realtime.protocol import rate_limit_warnings
from cube_petit_chat.nodes.realtime.session import RealtimeSession
from cube_petit_chat.nodes.util.history_logic import format_history_entry
from cube_petit_chat.nodes.util.history_logic import parse_history_lines
from cube_petit_chat.nodes.util.name_logic import DEFAULT_ROBOT
from cube_petit_chat.nodes.util.name_logic import speech_action_server_name
from cube_petit_chat_msgs.srv import AddContext


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
                                    ('model', DEFAULT_REALTIME_MODEL),
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
                                    ('transcription_only', False),
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
        model = self.get_parameter('model').get_parameter_value().string_value
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

        # 2026-05-12 に OpenAI が Realtime API の beta shape を廃止したため、
        # model パラメータを実際に使って接続 URL を組み立て、OpenAI-Beta ヘッダは付けない (GA shape)。
        self.websocket_url = build_websocket_url(model)
        self.headers = build_websocket_headers(api_key)
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
        self.transcription_only = self.get_parameter('transcription_only').get_parameter_value().bool_value
        if self.transcription_only:
            self.get_logger().info(
                'transcription_only enabled: server_vad create_response/interrupt_response are disabled, '
                'this node will only publish transcripts and will not speak.')

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
            # Set when a barge-in arrives before the goal response; the goal is
            # cancelled as soon as the handle becomes available.
            self._cancel_pending = False

            self.get_logger().info('Waiting for speech server...')

            if not self.__action_client.wait_for_server(timeout_sec=5.0):
                self.get_logger().error('Speech server not available after 5 seconds. Shutting down.')
                rclpy.shutdown()
                sys.exit(1)
            else:
                self.get_logger().info('Realtime conversation is ready')

        self._session = RealtimeSession(url=self.websocket_url,
                                        headers=self.headers,
                                        send_queue=self.audio_send_queue,
                                        is_active=self._is_streaming_active,
                                        build_session_config=self._build_session_config,
                                        on_event=self._handle_server_event,
                                        logger=self.get_logger(),
                                        on_connect=self._set_websocket_ref,
                                        on_audio_chunk=self._record_outgoing_audio)

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
        images = [bytes(img.data) for img in request.images]
        message = build_context_message(request.role, request.context, images)
        await self._websocket_ref.send(json.dumps(message))

    def publish_realtime_status(self) -> None:
        """Comment."""
        self.status_publisher.publish(self.status_msg)

    def _is_streaming_active(self) -> bool:
        """Return whether audio streaming is currently active."""
        return self.status_msg.is_active

    def save_to_history(self, role: str, content: str) -> None:
        """Append role-content pair to history file."""
        if not self.use_history or not self.history_file:
            return
        try:
            entry = format_history_entry(role, content, datetime.now().isoformat(timespec='seconds'))
            with open(self.history_file, 'a', encoding='utf-8') as f:
                f.write(entry)
        except Exception as e:
            self.get_logger().warn(f'Failed to save history: {e}')

    def load_history(self) -> list:
        """Load conversation history as a list of dicts."""
        if not self.use_history or not self.history_file:
            return []
        try:
            with open(self.history_file, 'r', encoding='utf-8') as f:
                lines = f.readlines()[-15:]
            return parse_history_lines(lines)
        except FileNotFoundError:
            self.get_logger().info(f'History file {self.history_file} not found. Starting fresh.')
            return []

    # ----------------------------------------------------------------------------------##
    # Action Server: Speech
    # ----------------------------------------------------------------------------------##

    def _on_goal_response(self, future: Future) -> None:
        """Response when goal response is received."""
        goal_handle = future.result()
        if not goal_handle.accepted:
            self.get_logger().warn('Speech goal was rejected.')
            return
        self.get_logger().info('Speech goal accepted.')
        if self._cancel_pending:
            # A barge-in arrived before this response; cancel right away.
            # This runs on an executor thread, so do not block on the future here.
            self._cancel_pending = False
            self.get_logger().info('Cancel was requested before goal response; cancelling now.')
            goal_handle.cancel_goal_async()
            return
        self._speech_goal_handle = goal_handle

        result_future = goal_handle.get_result_async()

        def _on_result_done(fut: Future) -> None:
            self.get_logger().info('Speech goal completed.')
            self._speech_goal_handle = None

        result_future.add_done_callback(_on_result_done)

    def _goal_is_active(self, goal_handle: ClientGoalHandle) -> bool:
        """Return True if the goal may still be running on the server.

        Note: ClientGoalHandle has no is_done attribute in Jazzy — checking it
        raises AttributeError, which silently swallowed every cancel request.
        Judge by the goal status instead.
        """
        return goal_handle.status not in (GoalStatus.STATUS_SUCCEEDED, GoalStatus.STATUS_CANCELED,
                                          GoalStatus.STATUS_ABORTED)

    def _request_cancel(self, goal_handle: ClientGoalHandle) -> None:
        """Send a cancel request and wait briefly for the response.

        The node is already spun by the main executor, so it must not be handed to
        another executor via rclpy.spin_until_future_complete() — doing so detaches
        the node from the main executor and leaves it orphaned afterwards, killing
        every ROS callback of this node. Wait on the future with an event instead.
        """
        cancel_future = goal_handle.cancel_goal_async()
        done = threading.Event()
        cancel_future.add_done_callback(lambda _future: done.set())
        if done.wait(timeout=1.0):
            self.get_logger().info('Speech goal cancelled.')
        else:
            self.get_logger().warn('Speech goal cancel response timed out (request was still sent).')

    def cancel_speech(self) -> None:
        """Cancel the speech goal if active."""
        self.get_logger().info('Attempting to cancel the speech goal...')
        if self._speech_goal_handle:
            try:
                if self._goal_is_active(self._speech_goal_handle):
                    self._request_cancel(self._speech_goal_handle)
            except Exception as e:
                self.get_logger().warn(f'Cancel failed: {e}')
            finally:
                self._speech_goal_handle = None
        else:
            # The goal response may still be in flight; cancel it on arrival.
            self._cancel_pending = True
            self.get_logger().info('No goal handle yet; will cancel on goal response if one is in flight.')

    def _send_speech_goal(self, text: str) -> None:
        """Cancel the previous speech goal (if any) and send a new one."""
        if self.__action_client.wait_for_server(timeout_sec=5.0):
            if self._speech_goal_handle and self._goal_is_active(self._speech_goal_handle):
                try:
                    self._request_cancel(self._speech_goal_handle)
                except Exception as e:
                    self.get_logger().warn(f'Failed to cancel previous speech goal: {e}')
                finally:
                    self._speech_goal_handle = None
            self._cancel_pending = False
            self.__goal_template.text = text
            self.get_logger().info(self.__goal_template.text)
            future = self.__action_client.send_goal_async(self.__goal_template)
            future.add_done_callback(self._on_goal_response)
        else:
            self.get_logger().error('Speech action server not available.')

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

    def _publish_mic_chunk(self, pcm_bytes: bytes) -> None:
        """Publish a chunk of microphone audio read by the input pump."""
        if self.input_mic_publisher is not None:
            msg = AudioDataStamped()
            msg.header.stamp = self.get_clock().now().to_msg()
            msg.header.frame_id = 'mic'
            msg.audio.data = pcm_bytes
            self.input_mic_publisher.publish(msg)

    def _record_outgoing_audio(self, audio_data: bytes) -> None:
        """Buffer outgoing audio while an utterance is being recorded."""
        if self._recording_speech:
            self._speech_pcm_buffer.extend(audio_data)

    def _set_websocket_ref(self, websocket: websockets.ClientConnection) -> None:
        """Keep a reference to the current WebSocket connection."""
        self._websocket_ref = websocket

    # ----------------------------------------------------------------------------------##
    # Realtime session wiring
    # ----------------------------------------------------------------------------------##

    def _build_session_config(self) -> dict:
        """Build the session.update event, loading history and tools."""
        instructions = self.instructions
        if self.use_history:
            history = self.load_history()
            instructions = merge_history_into_instructions(history, self.instructions)

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

                    tool_yaml = realtime_tools.load_tool_yaml(yaml_path)
                    tools_yaml.append(tool_yaml)
                    self.get_logger().info(f"YAML loaded successfully: {tool_yaml.get('name')}")

                    tool_function = realtime_tools.load_tool_function(tool_name, py_path)
                    self.tool_functions[tool_name] = tool_function
                    self.get_logger().info(f'Loaded tool: {tool_name}')
                    self.all_tool_functions[tool_name] = tool_function

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

                    tool_yaml = realtime_tools.load_tool_yaml(yaml_path)
                    gpt_tools_yaml.append(tool_yaml)
                    self.get_logger().info(f"YAML loaded successfully: {tool_yaml.get('name')}")

                    tool_function = realtime_tools.load_tool_function(tool_name, py_path)
                    self.gpt_tool_functions[tool_name] = tool_function
                    self.get_logger().info(f'Loaded tool: {tool_name}')
                    self.all_tool_functions[tool_name] = tool_function

                except Exception as e:
                    self.get_logger().error(f'Failed to load tool {tool_name}: {e}')

        all_tools = []
        if self.use_tools and self.tool_names:
            all_tools.extend(tools_yaml)

        if self.use_gpt_tools and self.gpt_tool_names:
            all_tools.extend(gpt_tools_yaml)

        return build_session_update(instructions, self.use_speech_action, all_tools or None, self.transcription_only)

    async def _handle_server_event(self, response_data: dict,
                                   websocket: websockets.ClientConnection) -> Optional[bool]:
        """Reflect a server event to ROS. Returning True stops the receive loop (existing behavior)."""
        response_type = response_data.get('type')
        # Display the server response in real-time
        if response_type == 'response.function_call_arguments.done':
            name = response_data.get('name')
            call_id = response_data.get('call_id')
            args = response_data.get('arguments', '{}')
            self.get_logger().info(f'Function call: {name}({args})')
            if 'memory' in name:
                if self.audio_data_msg is None or len(self.audio_data_msg.audio.data) == 0:
                    self.get_logger().warn('No audio data available to publish')
                    return True
                self.audio_info_publisher.publish(self.audio_info_msg)
                self.audio_stamped_publisher.publish(self.audio_data_msg)
                self.get_logger().info(f'Published AudioDataStamped (bytes={len(self._speech_pcm_buffer)})')
                self._speech_pcm_buffer.clear()

            if name in self.all_tool_functions:
                try:
                    raw_args = response_data.get('arguments', '{}')
                    result = await realtime_tools.run_tool(self.all_tool_functions[name], raw_args)

                    # Return the tool output and ask the model to continue
                    for event in build_tool_result_events(call_id, result):
                        await websocket.send(json.dumps(event))

                except Exception as e:
                    self.get_logger().error(f'Error executing tool "{name}": {e}')

        if response_type == 'conversation.item.created':
            item = response_data.get('item', {})
            for message in extract_assistant_texts(item):
                text_msg = String()
                text_msg.data = f'assistant: {message}'
                self.text_publisher.publish(text_msg)
                self.save_to_history('assistant', message)
                self._send_speech_goal(message)
        if response_type in ('response.output_audio_transcript.delta', 'response.output_text.delta'):
            self.assistant_text += response_data['delta']
        # Retrieve the completion status of the server response
        elif response_type in ('response.output_audio_transcript.done', 'response.output_text.done'):

            text_msg = String()
            text_msg.data = f'robot: {self.assistant_text}'
            self.text_publisher.publish(text_msg)
            self.save_to_history('assistant', self.assistant_text)
            if response_type == 'response.output_text.done':
                self._send_speech_goal(self.assistant_text)
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
                    return True
                self.audio_info_publisher.publish(self.audio_info_msg)
                self.audio_stamped_publisher.publish(self.audio_data_msg)
                self.get_logger().info(f'Published AudioDataStamped (bytes={len(self._speech_pcm_buffer)})')
                self._speech_pcm_buffer.clear()
        # Retrieve rate limit information
        elif response_type == 'rate_limits.updated':
            for warning in rate_limit_warnings(response_data.get('rate_limits', [])):
                self.get_logger().warn(warning)
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
                return True
            human_msg = AudioDataStamped()
            human_msg.header.stamp = self.get_clock().now().to_msg()
            human_msg.header.frame_id = 'mic'
            human_msg.audio.data = bytes(self._speech_pcm_buffer)
            self.human_voice_publisher.publish(human_msg)
            self.get_logger().info(f'Published human_voice_stamped (bytes={len(self._speech_pcm_buffer)})')

            self.audio_data_msg.header.stamp = self.get_clock().now().to_msg()
            self.audio_data_msg.header.frame_id = 'mic'
            self.audio_data_msg.audio.data = bytes(self._speech_pcm_buffer)
        if 'type' in response_data and response_data['type'] == 'response.output_audio.delta':
            base64_audio_response = response_data['delta']
            if base64_audio_response:
                self.audio_receive_queue.put(decode_audio_delta(base64_audio_response))
        return None

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
            self.input_stream = audio_io.open_input_stream(self.sample_rate, self.channels, self.chunk)
            self.input_stream.start()
            self.audio_threads.append(
                threading.Thread(target=audio_io.pump_input_to_queue,
                                 args=(self.input_stream, self.chunk, self.audio_send_queue, self._is_streaming_active,
                                       self._publish_mic_chunk, self.get_logger()),
                                 daemon=True))
        else:
            self.audio_subscription = self.create_subscription(AudioDataStamped, 'audio_stamped', self.audio_callback,
                                                               10)
        # Audio stream received from the API
        if self.use_speech_action:
            self.output_stream = audio_io.open_output_stream(self.sample_rate, self.channels, self.chunk)
            self.output_stream.start()
            self.audio_threads.append(
                threading.Thread(target=audio_io.pump_queue_to_output,
                                 args=(self.output_stream, self.audio_receive_queue, self._is_streaming_active,
                                       self.get_logger()),
                                 daemon=True))

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
            task = loop.create_task(self._session.run())
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
