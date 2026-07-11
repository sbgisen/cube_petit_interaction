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
"""change_expression tool: change the robot's facial expression.

Publishes a single FaceExpression message to the facial-animation system's
expression command topic (fire-and-forget; no service/action involved).
"""

import asyncio
import json
import time

import rclpy

from cube_petit_chat.nodes.util.name_logic import DEFAULT_ROBOT
from cube_petit_facial_animation_msgs.msg import FaceExpression

# Absolute topic name (no reliance on namespace resolution; see name_logic.py docstring).
EXPRESSION_TOPIC = f'/{DEFAULT_ROBOT}/facial_expression/expression_command'

# Valid expressions come from the FaceExpression message constants.
VALID_EXPRESSIONS = (
    FaceExpression.FACE_NORMAL,
    FaceExpression.FACE_HAPPY,
    FaceExpression.FACE_ANGRY,
    FaceExpression.FACE_SAD,
    FaceExpression.FACE_PUZZLED,
)

# Time to wait for the facial-animation subscriber to match with our fresh publisher.
# Publishing immediately after creating a publisher drops the message because DDS
# discovery has not completed yet, so poll get_subscription_count() first.
_SUBSCRIBER_MATCH_TIMEOUT_SEC = 2.0


def change_expression_sync(expression: str) -> str:
    """Publish one FaceExpression message to the expression command topic (blocking).

    Run in a worker thread by change_expression() so the realtime websocket loop
    keeps receiving events while waiting for the subscriber to match.

    Parameters
    ----------
    expression : str
        Expression name to switch to (one of VALID_EXPRESSIONS).

    Returns:
    -------
    str
        Result message for the realtime session (never raises).
    """
    node = None
    try:
        if not rclpy.ok():
            rclpy.init(args=None)
        # use_global_arguments=False: this tool runs inside the realtime node's process,
        # whose global --ros-args (-r __ns:=<robot>, -r __node:=realtime_gpt_chat) would
        # otherwise rename this throwaway node and re-namespace relative names.
        node = rclpy.create_node('change_expression_tool', use_global_arguments=False)

        publisher = node.create_publisher(FaceExpression, EXPRESSION_TOPIC, 10)

        # Wait until the facial-animation subscriber is matched; a publish issued
        # before DDS discovery completes would be silently dropped.
        deadline = time.monotonic() + _SUBSCRIBER_MATCH_TIMEOUT_SEC
        while publisher.get_subscription_count() == 0 and time.monotonic() < deadline:
            time.sleep(0.05)

        matched = publisher.get_subscription_count() > 0
        publisher.publish(FaceExpression(expression=expression))
        node.get_logger().info(f'Published expression command: {expression} (matched={matched})')

        if not matched:
            return f'表情を{expression}に変える指示は出したけど、表情システムが起動していないかも。'
        return f'表情を{expression}に変えたよ。'

    except Exception as e:
        return f'Error occurred while changing the expression: {e}'

    finally:
        if node is not None:
            node.destroy_node()


async def change_expression(arguments: dict) -> str:
    """Entry point called by the realtime node when the change_expression function is invoked.

    Parameters
    ----------
    arguments : dict
        Function-call arguments from the realtime API ({'expression': str}).

    Returns:
    -------
    str
        Result message to feed back to the realtime session.
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

        expression = args.get('expression', '')
        if expression not in VALID_EXPRESSIONS:
            valid_list = ', '.join(VALID_EXPRESSIONS)
            return f'「{expression}」という表情はできないよ。できる表情は {valid_list} だよ。'

        # Run the blocking publish in a worker thread so the realtime websocket
        # loop keeps receiving events while waiting for the subscriber match.
        loop = asyncio.get_running_loop()
        result_text = await loop.run_in_executor(None, change_expression_sync, expression)
        return f'{result_text}'

    except Exception as e:
        return f'Failed to handle change_expression call: {e}'
