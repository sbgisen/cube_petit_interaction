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
"""infer_object tool: grab one camera frame and ask GPT (vision) what it shows.

Reuses the same gpt_chat/chat service as the gpt_chat tool (see gpt_chat.py); the
only difference is that this tool attaches a single camera frame to the request.
"""

import asyncio
import json
import time
from typing import Optional

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy
from rclpy.qos import HistoryPolicy
from rclpy.qos import QoSProfile
from rclpy.qos import ReliabilityPolicy
from rclpy.task import Future
from sensor_msgs.msg import Image

from cube_petit_chat.nodes.util.name_logic import DEFAULT_ROBOT
from cube_petit_chat_msgs.srv import Chat

# Absolute topic name (no reliance on namespace resolution; see name_logic.py docstring).
CAMERA_TOPIC = f'/{DEFAULT_ROBOT}/camera/camera/color/image_raw'

SUPPLEMENTARY_INSTRUCTION = '画像に写っている、カメラに見せられている物について短く答えて。'

# Fallback QoS used only when no publisher could be discovered on the topic yet.
# NOTE: verified on the real robot (2026-07) that the color image_raw publisher is
# actually RELIABLE, not BEST_EFFORT as the sensor-data profile assumes; a BEST_EFFORT
# subscriber never receives frames from it in practice with rmw_cyclonedds_cpp. We
# therefore discover and match the publisher's actual QoS (see _resolve_image_qos)
# instead of hardcoding qos_profile_sensor_data, and only fall back to this profile.
_FALLBACK_IMAGE_QOS = QoSProfile(history=HistoryPolicy.KEEP_LAST,
                                 depth=5,
                                 reliability=ReliabilityPolicy.RELIABLE,
                                 durability=DurabilityPolicy.VOLATILE)


def _resolve_image_qos(node: Node, topic: str, discovery_timeout_sec: float = 1.5) -> QoSProfile:
    """Discover the actual QoS profile of a topic's publisher, to guarantee a compatible match.

    Parameters
    ----------
    node : Node
        Node used to query publisher endpoint info.
    topic : str
        Absolute topic name to inspect.
    discovery_timeout_sec : float
        Maximum time to wait for a publisher to be discovered.

    Returns:
    -------
    QoSProfile
        The discovered publisher's QoS profile, or a reliable fallback if none was found.
    """
    deadline = time.monotonic() + discovery_timeout_sec
    while time.monotonic() < deadline:
        infos = node.get_publishers_info_by_topic(topic)
        if infos:
            return infos[0].qos_profile
        rclpy.spin_once(node, timeout_sec=0.1)
    return _FALLBACK_IMAGE_QOS


def capture_one_image(node: Node, topic: str, timeout_sec: float = 5.0) -> Optional[Image]:
    """Subscribe to a camera topic and wait for a single frame.

    Parameters
    ----------
    node : Node
        Node used to create the (temporary) subscription.
    topic : str
        Absolute topic name to subscribe to.
    timeout_sec : float
        Overall time budget for QoS discovery and waiting for a frame.

    Returns:
    -------
    Optional[Image]
        The first received image, or None if none arrived within the timeout.
    """
    deadline = time.monotonic() + timeout_sec
    qos = _resolve_image_qos(node, topic, discovery_timeout_sec=min(1.5, timeout_sec))
    remaining_sec = max(0.0, deadline - time.monotonic())

    image_future: Future = Future()

    def _on_image(msg: Image) -> None:
        if not image_future.done():
            image_future.set_result(msg)

    subscription = node.create_subscription(Image, topic, _on_image, qos)
    try:
        rclpy.spin_until_future_complete(node, image_future, timeout_sec=remaining_sec)
        return image_future.result() if image_future.done() else None
    finally:
        node.destroy_subscription(subscription)


def infer_object_sync(question: str) -> str:
    """Capture a camera frame and ask the gpt_chat service what it shows (blocking).

    Run in a worker thread by infer_object() so the realtime websocket loop keeps
    receiving events while the image is captured and GPT is thinking.

    Parameters
    ----------
    question : str
        The user's question (e.g. "これは何?").

    Returns:
    -------
    str
        Chat response text (or an error message on failure).
    """
    node = None
    try:
        if not rclpy.ok():
            rclpy.init(args=None)
        node = rclpy.create_node('infer_object_tool')

        image_msg = capture_one_image(node, CAMERA_TOPIC, timeout_sec=5.0)
        if image_msg is None:
            node.get_logger().warn(f'No image received from {CAMERA_TOPIC} within timeout')
            return 'カメラの映像が取れませんでした。'

        chat_client = node.create_client(Chat, 'gpt_chat/chat')
        # 15s covers the gpt_api_chat node's startup (uv + venv boot takes >5s), so the
        # first tool call fired right after launch doesn't race the service into a timeout.
        if not chat_client.wait_for_service(timeout_sec=15.0):
            node.get_logger().error('gpt_chat/chat service timeout')
            return '頭の準備がまだ終わっていないみたい。少し待ってからもう一度聞いてほしい、と伝えてください。'

        request = Chat.Request()
        request.text = f'{question}\n{SUPPLEMENTARY_INSTRUCTION}'
        request.images = [image_msg]
        future = chat_client.call_async(request)
        rclpy.spin_until_future_complete(node, future, timeout_sec=60.0)
        if not future.done():
            node.get_logger().error('gpt_chat/chat did not respond in time')
            return 'GPT chat service did not respond in time.'

        response = future.result()
        text_resp = response.response.replace('\n', '').replace('*', '')
        node.get_logger().info(f'infer_object gpt_chat service returned: {text_resp}')
        return text_resp or 'No response was returned from the GPT chat service.'

    except Exception as e:
        return f'Error occurred while inferring the object: {e}'

    finally:
        if node is not None:
            node.destroy_node()


async def infer_object(arguments: dict) -> str:
    """Entry point called by the realtime node when the infer_object function is invoked.

    Parameters
    ----------
    arguments : dict
        Function-call arguments from the realtime API ({'question': str}).

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

        question = args.get('question', '')
        # Run the blocking capture + service call in a worker thread so the realtime
        # websocket loop keeps receiving events while GPT is thinking.
        loop = asyncio.get_running_loop()
        result_text = await loop.run_in_executor(None, infer_object_sync, question)
        return f'{result_text}'

    except Exception as e:
        return f'Failed to handle infer_object call: {e}'
