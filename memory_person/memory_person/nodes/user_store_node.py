#!/usr/bin/env python

# Copyright (c) 2025 SoftBank Corp.
#
# <<licensetext>>

import rclpy
from rclpy.node import Node

from cube_petit_interaction_msgs.srv import CreateUser
from cube_petit_interaction_msgs.srv import UpdateInteraction
from memory_person.src.user_store import UserStore


class UserStoreNode(Node):

    def __init__(self) -> None:
        super().__init__('user_store_node')

        self.declare_parameter('db_path', 'users.db')
        db_path = self.get_parameter('db_path').value

        self.store = UserStore(db_path)

        self.get_logger().info('UserStoreNode started')

        self.create_service(CreateUser, 'create_user', self.handle_create_user)
        self.create_service(UpdateInteraction, 'update_interaction', self.handle_update_interaction)

    def handle_update_interaction(self, request: UpdateInteraction.Request,
                                  response: UpdateInteraction.Response) -> UpdateInteraction.Response:

        user = self.store.get_user(request.user_id)

        if user is None:
            response.success = False
            response.confidence = 0.0
            response.interaction_count = 0
            return response

        self.store.update_interaction(request.user_id)

        updated_user = self.store.get_user(request.user_id)

        response.success = True
        response.confidence = float(updated_user.confidence)
        response.interaction_count = int(updated_user.interaction_count)

        self.get_logger().info(f'Updated interaction: {request.user_id} '
                               f'(count={updated_user.interaction_count})')

        return response

    def handle_create_user(self, request: CreateUser.Request, response: CreateUser.Response) -> CreateUser.Response:
        user = self.store.create_new_user()

        response.user_id = user.user_id
        response.confidence = float(user.confidence)
        response.interaction_count = int(user.interaction_count)

        self.get_logger().info(f'Created new user: {user.user_id}')

        return response

    def destroy_node(self) -> None:
        self.store.close()
        super().destroy_node()


def main() -> None:
    rclpy.init()
    node = UserStoreNode()
    rclpy.spin(node)
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
