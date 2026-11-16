#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from rclpy.action import ActionClient

from std_srvs.srv import SetBool
from ired_msgs.action import MoveToPoint

import time

class MoveAndTriggerClient(Node):

    def __init__(self):
        super().__init__('move_and_trigger_client')

        # Action Client
        self.move_client = ActionClient(
            self,
            MoveToPoint,
            '/ired/move_to_point'
        )

        # Service Client
        self.trigger_client = self.create_client(
            SetBool,
            '/arduino_q/trigger'
        )

        self.get_logger().info("Waiting for action server...")
        self.move_client.wait_for_server()

        self.get_logger().info("Waiting for service server...")
        while not self.trigger_client.wait_for_service(timeout_sec=1.0):
            self.get_logger().info("Service not available, waiting...")

    # -------------------------------
    # Move Function
    # -------------------------------

    def move_to_point(self, x, y, theta):

        goal_msg = MoveToPoint.Goal()

        goal_msg.x = x
        goal_msg.y = y
        goal_msg.theta = theta

        self.get_logger().info(
            f"Sending goal: x={x}, y={y}, theta={theta}"
        )

        send_goal_future = self.move_client.send_goal_async(goal_msg)

        rclpy.spin_until_future_complete(self, send_goal_future)

        goal_handle = send_goal_future.result()

        if not goal_handle.accepted:
            self.get_logger().error("Goal rejected!")
            return False

        self.get_logger().info("Goal accepted")

        result_future = goal_handle.get_result_async()

        rclpy.spin_until_future_complete(self, result_future)

        result = result_future.result().result

        self.get_logger().info(
            f"Result: {result.message}"
        )

        return result.success

    # -------------------------------
    # Arduino Trigger Function
    # -------------------------------

    def trigger_arduino(self, state):

        request = SetBool.Request()
        request.data = state

        self.get_logger().info(
            f"Trigger Arduino: {state}"
        )

        future = self.trigger_client.call_async(request)

        rclpy.spin_until_future_complete(self, future)

        response = future.result()

        if response is not None:

            self.get_logger().info(
                f"Service response: {response.message}"
            )

            return response.success

        else:

            self.get_logger().error("Service call failed")
            return False


# ======================================================
# Main Loop
# ======================================================

def main(args=None):

    rclpy.init(args=args)

    node = MoveAndTriggerClient()

    try:

        while rclpy.ok():

            # Move to first point
            success = node.move_to_point(
                0.837,
                0.71,
                1.57
            )

            if success:
                node.trigger_arduino(True)

            time.sleep(5)

            # Move to second point
            success = node.move_to_point(
                3.09,
                2.48,
                0.0
            )

            if success:
                node.trigger_arduino(False)

            time.sleep(5)

    except KeyboardInterrupt:

        node.get_logger().info("Stopped by user")

    finally:

        node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()