#!/usr/bin/env python

# Copyright (c) 2026 SoftBank Corp.
# 
# <<licensetext>>
from rclpy.node import Node
from cube_petit_chat_msgs.srv import Chat, AddContext
from std_srvs.srv import Trigger
from sensor_msgs.msg import Image
import rclpy


class GPTCommander:

    def __init__(self, node: Node):
        self._node = node

        self._chat_client = node.create_client(Chat, 'chat')
        self._context_client = node.create_client(AddContext, 'add_chat_context')
        self._clear_client = node.create_client(Trigger, 'clear_chat_history')

        self._chat_client.wait_for_service()
        self._context_client.wait_for_service()
        self._clear_client.wait_for_service()

    def clear(self) -> bool:
        req = Trigger.Request()
        future = self._clear_client.call_async(req)
        rclpy.spin_until_future_complete(self._node, future)
        return future.result().success if future.result() else False

    def add_context(self, role: int, text: str, images: list[Image] = []) -> bool:
        req = AddContext.Request()
        req.role = role
        req.context = text
        req.images = images

        future = self._context_client.call_async(req)
        rclpy.spin_until_future_complete(self._node, future)
        return future.result().success if future.result() else False

    def chat(self, text: str, images: list[Image] = []) -> Chat.Response | None:
        req = Chat.Request()
        req.text = text
        req.images = images

        future = self._chat_client.call_async(req)
        rclpy.spin_until_future_complete(self._node, future)
        return future.result()
