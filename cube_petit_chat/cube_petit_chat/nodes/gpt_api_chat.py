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

import pathlib
import sys

from cube_petit_chat_msgs.srv._add_context import AddContext
from cube_petit_chat_msgs.srv._chat import Chat
import cv_bridge
import numpy as np
import rclpy
from rclpy.executors import ExternalShutdownException
from rclpy.node import Node
from std_srvs.srv import Trigger
from vision_msgs.msg import BoundingBox2DArray

from cube_petit_chat.nodes.util.gpt_client import GPTClient

# -------------------------------
# Vision Detection Function
# -------------------------------
VISION_FUNCTION = {
    'type': 'function',
    'name': 'report_detections',
    'description': 'Report detected objects with bounding boxes',
    'parameters': {
        'type': 'object',
        'properties': {
            'response': {
                'type': 'string'
            },
            'detections': {
                'type': 'array',
                'items': {
                    'type': 'object',
                    'properties': {
                        'label': {
                            'type': 'string'
                        },
                        'x': {
                            'type': 'number'
                        },
                        'y': {
                            'type': 'number'
                        },
                        'width': {
                            'type': 'number'
                        },
                        'height': {
                            'type': 'number'
                        }
                    },
                    'required': ['label', 'x', 'y', 'width', 'height']
                }
            }
        },
        'required': ['response', 'detections']
    }
}


class GPTChat(Node):
    ROLE_MAP = {0: 'system', 1: 'assistant', 2: 'user'}

    def __init__(self) -> None:
        """Initialize the class instance."""
        super().__init__('gpt_chat')
        self.declare_parameters(namespace='',
                                parameters=[
                                    ('api_key', ''),
                                    ('model', 'gpt-4o'),
                                    ('vision_model', 'gpt-4o'),
                                    ('max_tokens', 1000),
                                    ('max_turns', 2),
                                    ('detail', 'auto'),
                                    ('setting_file', ''),
                                    ('enable_web_search', False),
                                ])
        api_key = self.get_parameter('api_key').get_parameter_value().string_value
        model = self.get_parameter('model').get_parameter_value().string_value
        vision_model = self.get_parameter('vision_model').get_parameter_value().string_value
        setting_file = self.get_parameter('setting_file').get_parameter_value().string_value
        max_tokens = self.get_parameter('max_tokens').get_parameter_value().integer_value
        enable_web_search = self.get_parameter('enable_web_search').get_parameter_value().bool_value
        self.__cv_bridge = cv_bridge.CvBridge()
        self.create_service(Chat, 'chat', self.__gpt_chat_callback)
        self.create_service(AddContext, 'add_chat_context', self.__add_context_callback)
        self.create_service(Trigger, 'clear_chat_history', self.__clear_history_callback)

        if not api_key:
            self.get_logger().error('API key is empty.')
            raise RuntimeError('API key must be provided.')

        instructions_path = pathlib.Path(setting_file) if setting_file else None
        self.client = GPTClient(api_key=api_key,
                                model_name=model,
                                max_tokens=max_tokens,
                                instructions_file=instructions_path,
                                enable_web_search=enable_web_search)
        self._bridge = cv_bridge.CvBridge()
        self.get_logger().info('GPTChat node started.')

    # ==========================================================
    # Chat
    # ==========================================================
    def __gpt_chat_callback(self, req: Chat.Request, resp: Chat.Response) -> Chat.Response:
        try:
            images_np = self._convert_images(req.images) if req.images else []

            if not req.text and not images_np:
                return resp

            self.client.add_context(role='user', text=req.text if req.text else None, images=images_np)

            # 👇 ここが重要
            response = self.client.chat(functions=[VISION_FUNCTION])

            if hasattr(response, 'output'):
                for item in response.output:
                    if item.type == 'message':
                        text = ''.join(block.text for block in item.content if hasattr(block, 'text'))
                        if text:
                            resp.response = text
                            resp.labels = []
                            resp.boxes = BoundingBox2DArray()
                            return resp

            # 通常テキスト応答
            if isinstance(response, str):
                resp.response = response
                resp.labels = []
                resp.boxes = BoundingBox2DArray()
                return resp

            # FunctionCallが来た場合
            if hasattr(response, 'output'):
                for item in response.output:
                    if item.type == 'tool_call' and item.name == 'report_detections':
                        data = item.arguments

                        resp.response = data['response']
                        resp.labels = []

                        bbox_array = BoundingBox2DArray()

                        for det in data['detections']:
                            resp.labels.append(det['label'])
                            bbox_array.boxes.append(self._create_bbox(det))

                        resp.boxes = bbox_array
                        return resp

            # fallback
            resp.response = ''
            resp.labels = []
            resp.boxes = BoundingBox2DArray()

        except Exception as e:
            self.get_logger().error(f'Vision chat failed: {e}')

        return resp

    # ==========================================================
    # Add Context
    # ==========================================================

    def __add_context_callback(self, req: AddContext.Request, res: AddContext.Response) -> AddContext.Response:
        try:
            role_str = self.ROLE_MAP.get(req.role, 'user')

            images_np = self._convert_images(req.images) if req.images else []

            if not req.text and not images_np:
                self.get_logger().warn('Empty chat request.')
                res.response = ''
                res.labels = []
                res.boxes = BoundingBox2DArray()
                return res

            self.client.add_context(role=role_str, text=req.context, images=images_np)

            res.success = True

        except Exception as e:
            self.get_logger().error(f'Add context failed: {e}')
            res.success = False

        return res

    # ==========================================================
    # Clear History
    # ==========================================================

    def __clear_history_callback(self, request: Trigger.Request, response: Trigger.Response) -> Trigger.Response:
        try:
            self.client.clear_context()
            response.success = True
            response.message = 'Chat history cleared.'
        except Exception as e:
            self.get_logger().error(f'Clear history failed: {e}')
            response.success = False
            response.message = str(e)

        return response

    # ==========================================================
    # Utility
    # ==========================================================

    def _convert_images(self, ros_images) -> list[np.ndarray]:
        images_np = []
        for img_msg in ros_images:
            try:
                cv_img = self._bridge.imgmsg_to_cv2(img_msg, desired_encoding='bgr8')
                images_np.append(cv_img)
            except Exception as e:
                self.get_logger().warn(f'Image conversion failed: {e}')
        return images_np


# ==========================================================
# Main
# ==========================================================


def main() -> None:
    rclpy.init()

    try:
        node = GPTChat()
        rclpy.spin(node)

    except KeyboardInterrupt:
        pass

    except ExternalShutdownException:
        sys.exit(1)

    finally:
        rclpy.try_shutdown()


if __name__ == '__main__':
    main()
