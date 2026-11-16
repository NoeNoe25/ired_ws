# #!/usr/bin/env python3
# """Robot pose -> zone + box angle, from /amcl_pose (map frame).

# Publishes /pose_zone (std_msgs/String) at `rate` Hz:
#   {"x": 4.5, "y": 0.5, "zone": "C_Z51", "robot_yaw_deg": 180.0, "box_angle": 0}
# Logs the latest value every 3 s.
# """
# import json
# import time
# from math import atan2, degrees, floor

# import rclpy
# from rclpy.node import Node
# from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
# from geometry_msgs.msg import PoseWithCovarianceStamped
# from std_msgs.msg import String

# LOG_PERIOD = 3.0   # seconds between log lines


# def calculate_zone(x, y):
#     col, row = floor(x), floor(y)
#     if not (0 <= col < 5 and 0 <= row < 5):
#         return 'Outside map'
#     return f'C_Z{col + 1}{row + 1}'


# def yaw_deg(q):
#     return degrees(atan2(2.0 * (q.w * q.z + q.x * q.y),
#                          1.0 - 2.0 * (q.y * q.y + q.z * q.z))) % 360.0


# def box_angle(robot_yaw):
#     """Robot facing 180 -> box 0, robot 90 -> box 270. Rounded to 45 deg."""
#     return (floor(((robot_yaw - 180.0) % 360.0 + 22.5) / 45.0) * 45) % 360


# class PoseZoneNode(Node):
#     def __init__(self):
#         super().__init__('pose_zone_node')
#         rate = float(self.declare_parameter('rate', 5.0).value)

#         self.out = None
#         self.last_log = 0.0

#         qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
#                          durability=DurabilityPolicy.TRANSIENT_LOCAL)
#         self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', self.on_amcl, qos)
#         self.pub = self.create_publisher(String, '/pose_zone', 10)
#         self.create_timer(1.0 / rate, self.publish)

#         self.get_logger().info('Waiting for /amcl_pose (set 2D Pose Estimate in RViz)...')

#     def on_amcl(self, msg):
#         p = msg.pose.pose
#         x, y = p.position.x, p.position.y
#         yaw = yaw_deg(p.orientation)
#         self.out = {
#             'x': round(x, 3),
#             'y': round(y, 3),
#             'zone': calculate_zone(x, y),
#             'robot_yaw_deg': round(yaw, 1),
#             'box_angle': box_angle(yaw),
#         }

#     def publish(self):
#         if self.out is None:
#             return
#         data = json.dumps(self.out)
#         self.pub.publish(String(data=data))
#         now = time.time()
#         if now - self.last_log >= LOG_PERIOD:
#             self.get_logger().info(data)
#             self.last_log = now


# def main():
#     rclpy.init()
#     node = PoseZoneNode()
#     try:
#         rclpy.spin(node)
#     except KeyboardInterrupt:
#         pass
#     finally:
#         node.destroy_node()
#         if rclpy.ok():
#             rclpy.shutdown()


# if __name__ == '__main__':
#     main()

#!/usr/bin/env python3
"""Robot pose + ArUco yaw -> zone + box angle.

Inputs:
  /amcl_pose          robot x, y, yaw (map frame)
  /aruco/detections   {"markers": [{"id": 101, "machine": "CS1", "side": "output", "marker_yaw": -12.3}]}

Publishes /pose_zone (std_msgs/String) at `rate` Hz:
  {"x": 4.5, "y": 0.5, "zone": "C_Z51", "robot_yaw_deg": 180.0, "aruco_yaw": -12.3, "box_angle": 0}

box_angle = robot_yaw - 180 + aruco_yaw, snapped to 45 deg.
aruco_yaw = 0 when no marker was seen in the last ARUCO_TIMEOUT s.
Logs x, y, zone, aruco_yaw, box_angle every 3 s.
"""
import json
import time
from math import atan2, degrees, floor

import rclpy
from rclpy.node import Node
from rclpy.qos import QoSProfile, ReliabilityPolicy, DurabilityPolicy
from geometry_msgs.msg import PoseWithCovarianceStamped
from std_msgs.msg import String

LOG_PERIOD = 3.0      # seconds between log lines
ARUCO_TIMEOUT = 1.0   # aruco_yaw older than this -> 0
ARUCO_SIGN = 1        # set to -1 if the box angle turns the wrong way


def calculate_zone(x, y):
    col, row = floor(x), floor(y)
    if not (0 <= col < 5 and 0 <= row < 5):
        return 'Outside map'
    return f'C_Z{col + 1}{row + 1}'


def yaw_deg(q):
    return degrees(atan2(2.0 * (q.w * q.z + q.x * q.y),
                         1.0 - 2.0 * (q.y * q.y + q.z * q.z))) % 360.0


def snap45(angle):
    return (floor((angle % 360.0 + 22.5) / 45.0) * 45) % 360


def box_angle(robot_yaw, aruco_yaw):
    """Robot facing 180 + marker straight on -> box 0; robot 90 -> box 270."""
    return snap45(robot_yaw - 180.0 + ARUCO_SIGN * aruco_yaw)


class PoseZoneNode(Node):
    def __init__(self):
        super().__init__('pose_zone_node')
        rate = float(self.declare_parameter('rate', 5.0).value)

        self.robot = None          # (x, y, yaw)
        self.aruco_yaw = 0.0
        self.aruco_t = 0.0
        self.last_log = 0.0

        qos = QoSProfile(depth=1, reliability=ReliabilityPolicy.RELIABLE,
                         durability=DurabilityPolicy.TRANSIENT_LOCAL)
        self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', self.on_amcl, qos)
        self.create_subscription(String, '/aruco/detections', self.on_aruco, 10)
        self.pub = self.create_publisher(String, '/pose_zone', 10)
        self.create_timer(1.0 / rate, self.publish)

        self.get_logger().info('Waiting for /amcl_pose (set 2D Pose Estimate in RViz)...')

    def on_amcl(self, msg):
        p = msg.pose.pose
        self.robot = (p.position.x, p.position.y, yaw_deg(p.orientation))

    def on_aruco(self, msg):
        try:
            markers = json.loads(msg.data).get('markers', [])
        except json.JSONDecodeError:
            return
        if markers:
            self.aruco_yaw = float(markers[0].get('marker_yaw', 0.0))
            self.aruco_t = time.time()

    def publish(self):
        if self.robot is None:
            return
        x, y, ryaw = self.robot
        now = time.time()
        ayaw = self.aruco_yaw if now - self.aruco_t <= ARUCO_TIMEOUT else 0.0
        out = {
            'x': round(x, 3),
            'y': round(y, 3),
            'zone': calculate_zone(x, y),
            'robot_yaw_deg': round(ryaw, 1),
            'aruco_yaw': round(ayaw, 1),
            'box_angle': box_angle(ryaw, ayaw),
        }
        self.pub.publish(String(data=json.dumps(out)))
        if now - self.last_log >= LOG_PERIOD:
            self.get_logger().info(f"x={out['x']:.2f} y={out['y']:.2f} zone={out['zone']} "
                                   f"aruco_yaw={out['aruco_yaw']:+.1f} box_angle={out['box_angle']}")
            self.last_log = now


def main():
    rclpy.init()
    node = PoseZoneNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()