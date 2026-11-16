#!/usr/bin/env python3

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import JointState


class JointStateTest(Node):

    def __init__(self):
        super().__init__('joint_state_test')

        self.publisher = self.create_publisher(
            JointState,
            '/joint_states',
            10
        )

        self.timer = self.create_timer(
            0.1,
            self.publish_joint_states
        )

    def publish_joint_states(self):

        msg = JointState()

        msg.header.stamp = self.get_clock().now().to_msg()

        msg.name = [
            'wheel_front_left_joint',
            'wheel_front_right_joint',
            'wheel_rear_left_joint',
            'wheel_rear_right_joint'
        ]

        # Keep wheels stationary for RViz
        msg.position = [
            0.0,
            0.0,
            0.0,
            0.0
        ]

        msg.velocity = [
            0.0,
            0.0,
            0.0,
            0.0
        ]

        self.publisher.publish(msg)


def main(args=None):

    rclpy.init(args=args)

    node = JointStateTest()

    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass

    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main()
