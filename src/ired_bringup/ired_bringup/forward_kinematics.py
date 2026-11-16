
# import rclpy
# from rclpy.node import Node

# from geometry_msgs.msg import TwistStamped
# from ired_msgs.msg import MotorData


# class FORWARDKINEMATICS(Node):

#     def __init__(self):
#         super().__init__('forward_kinematics_node')

#         # Initialise Variables and Parameters
#         self.initial_parameters()
#         self.initial_variables()

#         # Initialise ROS Publisher and Subscriber
#         self.robot_speed_pub = self.create_publisher(
#             TwistStamped,
#             self.forward_kinematics_topic,
#             10
#         )

#         self.create_subscription(
#             MotorData,
#             self.motor_data_topic,
#             self.fetchMotorSpeedCallback,
#             10
#         )

#         # Initialise ROS Timer
#         timer_period = 0.1  # seconds
#         self.timer = self.create_timer(
#             timer_period,
#             self.update_callback
#         )

#         # ROS Logger
#         self.get_logger().info(
#             f"Forward : ROS publisher on "
#             f"{self.forward_kinematics_topic} "
#             f"[geometry_msgs/TwistStamped]"
#         )

#         self.get_logger().info(
#             f"Forward : ROS subscriber on "
#             f"{self.motor_data_topic} "
#             f"[ired_msgs/MotorData]"
#         )

#     # =========================================================
#     # PARAMETERS
#     # =========================================================

#     def initial_parameters(self):

#         # Declare parameters
#         self.declare_parameter(
#             'motor_data_topic',
#             '/ired/motor/data'
#         )

#         self.declare_parameter(
#             'robot_speed_topic',
#             '/ired/speed'
#         )

#         self.declare_parameter(
#             'wheel_seperation',
#             0.4
#         )

#         self.declare_parameter(
#             'rpm_to_mps',
#             0.006544984695
#         )

#         # Get parameters
#         self.motor_data_topic = (
#             self.get_parameter('motor_data_topic')
#             .get_parameter_value()
#             .string_value
#         )

#         self.forward_kinematics_topic = (
#             self.get_parameter('robot_speed_topic')
#             .get_parameter_value()
#             .string_value
#         )

#         self.wheel_seperation = (
#             self.get_parameter('wheel_seperation')
#             .get_parameter_value()
#             .double_value
#         )

#         self.rpm_to_mps = (
#             self.get_parameter('rpm_to_mps')
#             .get_parameter_value()
#             .double_value
#         )

#     # =========================================================
#     # VARIABLES
#     # =========================================================

#     def initial_variables(self):

#         # Wheel speed feedback
#         # [FLEFT, FRIGHT, RLEFT, RRIGHT]
#         self.wheel_speed_fb = [
#             0.0,
#             0.0,
#             0.0,
#             0.0
#         ]

#         # Robot velocity
#         self.robot_speed = TwistStamped()

#         self.robot_speed.twist.linear.x = 0.0
#         self.robot_speed.twist.linear.y = 0.0
#         self.robot_speed.twist.linear.z = 0.0

#         self.robot_speed.twist.angular.x = 0.0
#         self.robot_speed.twist.angular.y = 0.0
#         self.robot_speed.twist.angular.z = 0.0

#         # Wheel indices
#         self.FLEFT = 0
#         self.FRIGHT = 1
#         self.RLEFT = 2
#         self.RRIGHT = 3

#         # Time of last motor feedback
#         self.last_time_speed_fb = self.get_clock().now()

#     # =========================================================
#     # MOTOR SPEED CALLBACK
#     # =========================================================

#     def fetchMotorSpeedCallback(self, msg):

#         self.last_time_speed_fb = self.get_clock().now()

#         # Motor feedback is in RPM
#         self.wheel_speed_fb = list(msg.speed_fb)

#     # =========================================================
#     # FORWARD KINEMATICS
#     # =========================================================

#     def calculateForwardKinematics(self):

#         # -----------------------------------------------------
#         # Get individual wheel speeds
#         #
#         # speed_fb is in RPM
#         #
#         # [FLEFT, FRIGHT, RLEFT, RRIGHT]
#         # [  0,     1,     2,     3]
#         # -----------------------------------------------------

#         front_left_rpm = self.wheel_speed_fb[self.FLEFT]
#         front_right_rpm = self.wheel_speed_fb[self.FRIGHT]

#         rear_left_rpm = self.wheel_speed_fb[self.RLEFT]
#         rear_right_rpm = self.wheel_speed_fb[self.RRIGHT]

#         # -----------------------------------------------------
#         # Convert RPM -> m/s
#         # -----------------------------------------------------

#         front_left_velocity = (
#             front_left_rpm * self.rpm_to_mps
#         )

#         front_right_velocity = (
#             front_right_rpm * self.rpm_to_mps
#         )

#         rear_left_velocity = (
#             rear_left_rpm * self.rpm_to_mps
#         )

#         rear_right_velocity = (
#             rear_right_rpm * self.rpm_to_mps
#         )

#         # -----------------------------------------------------
#         # Average front and rear wheels on each side
#         #
#         # Left side:
#         # v_left = (FL + RL) / 2
#         #
#         # Right side:
#         # v_right = (FR + RR) / 2
#         # -----------------------------------------------------

#         left_velocity = (
#             front_left_velocity +
#             rear_left_velocity
#         ) / 2.0

#         right_velocity = (
#             front_right_velocity +
#             rear_right_velocity
#         ) / 2.0

#         # -----------------------------------------------------
#         # Differential drive forward kinematics
#         #
#         # v = (v_right + v_left) / 2
#         #
#         # omega = (v_right - v_left) / L
#         # -----------------------------------------------------

#         linear_velocity = (
#             left_velocity +
#             right_velocity
#         ) / 2.0

#         angular_velocity = (
#             right_velocity -
#             left_velocity
#         ) / self.wheel_seperation

#         # -----------------------------------------------------
#         # Set robot velocity
#         # -----------------------------------------------------

#         self.robot_speed.twist.linear.x = linear_velocity

#         # Differential-drive robot
#         # does not directly control Y velocity
#         self.robot_speed.twist.linear.y = 0.0
#         self.robot_speed.twist.linear.z = 0.0

#         self.robot_speed.twist.angular.x = 0.0
#         self.robot_speed.twist.angular.y = 0.0
#         self.robot_speed.twist.angular.z = angular_velocity

#     # =========================================================
#     # UPDATE CALLBACK
#     # =========================================================

#     def update_callback(self):

#         time_now = self.get_clock().now()

#         # -----------------------------------------------------
#         # Safety timeout
#         #
#         # If no motor feedback is received for more than
#         # 1 second, assume all wheels have stopped.
#         # -----------------------------------------------------

#         time_since_speed_fb = (
#             time_now - self.last_time_speed_fb
#         ).nanoseconds / 1e9

#         if time_since_speed_fb > 1.0:

#             self.wheel_speed_fb = [
#                 0.0,
#                 0.0,
#                 0.0,
#                 0.0
#             ]

#         # Calculate forward kinematics
#         self.calculateForwardKinematics()

#         # Update timestamp
#         self.robot_speed.header.stamp = (
#             self.get_clock().now().to_msg()
#         )

#         # Publish robot velocity
#         self.robot_speed_pub.publish(
#             self.robot_speed
#         )


# # =============================================================
# # MAIN
# # =============================================================

# def main(args=None):

#     rclpy.init(args=args)

#     forward_kinematics = FORWARDKINEMATICS()

#     rclpy.spin(forward_kinematics)

#     forward_kinematics.destroy_node()

#     rclpy.shutdown()


# if __name__ == '__main__':
#     main()

#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

from geometry_msgs.msg import TwistStamped
from ired_msgs.msg import MotorData

class FORWARDKINEMATICS(Node):
    def __init__(self):
        super().__init__('forward_kinematics_node')
        
        # Initialise Variables and Parameters
        self.initial_parameters()
        self.initial_variables()
        
        # Initialise ROS Publisher and Subscriber
        self.robot_speed_pub = self.create_publisher(TwistStamped, self.forward_kinematics_topic, 10)
        self.create_subscription(MotorData, self.motor_data_topic, self.fetchMotorSpeedCallback, 10)
        
        # Initialise ROS Timers
        timer_period = 0.1 # seconds
        self.timer = self.create_timer(timer_period, self.update_callback)
        
        # ROS Logger
        self.get_logger().info(f"Forward : ROS publisher on {self.forward_kinematics_topic} [geometry_msgs/TwistStamped]")
        self.get_logger().info(f"Forward : ROS subscriber on {self.motor_data_topic} [ired_msgs/MotorData]")
    
    def initial_parameters(self):
        # Declare parameters
        self.declare_parameter('motor_data_topic', '/ired/motor/data')
        self.declare_parameter('robot_speedtopic', '/ired/speed')
        self.declare_parameter('wheel_seperation', 0.199)
        self.declare_parameter('rpm_to_mps', 0.003560471674)
        
        # ROS Parameters
        self.motor_data_topic = self.get_parameter('motor_data_topic').get_parameter_value().string_value
        self.forward_kinematics_topic = self.get_parameter('robot_speedtopic').get_parameter_value().string_value
        self.wheel_seperation = self.get_parameter('wheel_seperation').get_parameter_value().double_value
        self.rpm_to_mps = self.get_parameter('rpm_to_mps').get_parameter_value().double_value
    
    def initial_variables(self):
        self.wheel_speed_fb = [0.0, 0.0, 0.0, 0.0]
        self.robot_speed = TwistStamped()
        self.robot_speed.twist.linear.x = 0.0
        self.robot_speed.twist.linear.y = 0.0
        self.robot_speed.twist.linear.z = 0.0
        self.robot_speed.twist.angular.x = 0.0
        self.robot_speed.twist.angular.y = 0.0
        self.robot_speed.twist.angular.z = 0.0
        self.FLEFT = 0
        self.FRIGHT = 1
        self.RLEFT = 2
        self.RRIGHT = 3
        self.last_time_speed_fb = self.get_clock().now()
    
    def fetchMotorSpeedCallback(self, msg):
        self.last_time_speed_fb = self.get_clock().now()
        self.wheel_speed_fb = list(msg.speed_fb)
    
    def calculateForwardKinematics(self):

        # ---------------------------------------------------------
        # Wheel speed feedback
        #
        # [FLEFT, FRIGHT, RLEFT, RRIGHT]
        # ---------------------------------------------------------

        v_FL = self.wheel_speed_fb[self.FLEFT] * self.rpm_to_mps
        v_FR = self.wheel_speed_fb[self.FRIGHT] * self.rpm_to_mps
        v_RL = self.wheel_speed_fb[self.RLEFT] * self.rpm_to_mps
        v_RR = self.wheel_speed_fb[self.RRIGHT] * self.rpm_to_mps

        # ---------------------------------------------------------
        # Constants
        # ---------------------------------------------------------

        k = 0.7071067811865476

        # ---------------------------------------------------------
        # Forward Kinematics
        #
        # v_x = -1/2(
        #       -v_FL sin45
        #       -v_FR sin315
        #       -v_RL sin135
        #       -v_RR sin225
        #       )
        #
        # v_y = -1/2(
        #        v_FL cos45
        #       +v_FR cos315
        #       +v_RL cos135
        #       +v_RR cos225
        #       )
        # ---------------------------------------------------------

        # v_x = -0.5 * (
        #     -v_FL * k
        #     -v_FR * (-k)
        #     -v_RL * k
        #     -v_RR * (-k)
        # )

        # v_y = -0.5 * (
        #     v_FL * k
        #     +v_FR * k
        #     +v_RL * (-k)
        #     +v_RR * (-k)
        # )

        v_x = 0.5 * (
            -v_FL * k
            -v_FR * (-k)
            -v_RL * k
            -v_RR * (-k)
        )

        v_y = 0.5 * (
            v_FL * k
            +v_FR * k
            +v_RL * (-k)
            +v_RR * (-k)
        )

        # ---------------------------------------------------------
        # Angular velocity
        #
        # omega = -(1 / 4R) *
        #         (v_FL + v_FR + v_RL + v_RR)
        #
        # R = wheel_seperation / 2
        # ---------------------------------------------------------

        R = self.wheel_seperation / 2.0

        omega = -(
            v_FL + v_FR + v_RL + v_RR
        ) / (4.0 * R)

        # ---------------------------------------------------------
        # Robot velocity
        # ---------------------------------------------------------

        self.robot_speed.twist.linear.x = v_x
        self.robot_speed.twist.linear.y = v_y
        self.robot_speed.twist.linear.z = 0.0

        self.robot_speed.twist.angular.x = 0.0
        self.robot_speed.twist.angular.y = 0.0
        self.robot_speed.twist.angular.z = omega
        
    def update_callback(self):
        time_now = self.get_clock().now()
        
        if (time_now - self.last_time_speed_fb).nanoseconds / 1e9 > 1.0:
            self.wheel_speed_fb = [0.0] * 4
        
        self.calculateForwardKinematics()
        self.robot_speed.header.stamp = self.get_clock().now().to_msg()
        self.robot_speed_pub.publish(self.robot_speed)

def main(args=None):
    rclpy.init(args=args)
    forward_kinematics = FORWARDKINEMATICS()
    
    rclpy.spin(forward_kinematics)
    
    forward_kinematics.destroy_node()
    rclpy.shutdown()

if __name__ == '__main__':
    main()