# import rclpy
# from rclpy.node import Node

# from geometry_msgs.msg import TwistStamped
# from ired_msgs.msg import MotorSpeed


# class INVERSEKINEMATICS(Node):

#     def __init__(self):
#         super().__init__('inverse_kinematics_node')

#         # Initialise Variables and Parameters
#         self.initial_parameters()
#         self.initial_variables()

#         # Initialise ROS Publisher and Subscriber
#         self.speed_control_pub = self.create_publisher(
#             MotorSpeed,
#             self.inverse_kinematics_topic,
#             10
#         )

#         self.create_subscription(
#             TwistStamped,
#             self.cmd_vel_topic,
#             self.fetchCommandVelocityCallback,
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
#             f"Inverse : ROS publisher on "
#             f"{self.inverse_kinematics_topic} "
#             f"[ired_msgs/MotorSpeed]"
#         )

#         self.get_logger().info(
#             f"Inverse : ROS subscriber on "
#             f"{self.cmd_vel_topic} "
#             f"[geometry_msgs/TwistStamped]"
#         )

#     # =========================================================
#     # PARAMETERS
#     # =========================================================

#     def initial_parameters(self):

#         # Declare parameters
#         self.declare_parameter(
#             'cmd_vel_topic',
#             '/cmd_vel'
#         )

#         self.declare_parameter(
#             'motor_control_topic',
#             '/ired/motor/speed_control'
#         )

#         self.declare_parameter(
#             'wheel_seperation',
#             0.4
#         )

#         self.declare_parameter(
#             'mps_to_rpm',
#             152.78874537
#         )

#         # Get parameters
#         self.cmd_vel_topic = (
#             self.get_parameter('cmd_vel_topic')
#             .get_parameter_value()
#             .string_value
#         )

#         self.inverse_kinematics_topic = (
#             self.get_parameter('motor_control_topic')
#             .get_parameter_value()
#             .string_value
#         )

#         self.wheel_seperation = (
#             self.get_parameter('wheel_seperation')
#             .get_parameter_value()
#             .double_value
#         )

#         self.mps_to_rpm = (
#             self.get_parameter('mps_to_rpm')
#             .get_parameter_value()
#             .double_value
#         )

#     # =========================================================
#     # VARIABLES
#     # =========================================================

#     def initial_variables(self):

#         # Desired robot velocity
#         self.goal_linear_velocity_x = 0.0
#         self.goal_linear_velocity_y = 0.0
#         self.goal_angular_velocity_z = 0.0

#         # Wheel speed command
#         self.wheel_speed_cmd = [
#             0.0,
#             0.0,
#             0.0,
#             0.0
#         ]

#         # MotorSpeed message
#         self.motor_speed = MotorSpeed()
#         self.motor_speed.speed = [
#             0.0,
#             0.0,
#             0.0,
#             0.0
#         ]

#         # Wheel indices
#         self.FLEFT = 0
#         self.FRIGHT = 1
#         self.RLEFT = 2
#         self.RRIGHT = 3

#         # Time of last cmd_vel message
#         self.last_time_cmd_vel = self.get_clock().now()

#     # =========================================================
#     # CMD_VEL CALLBACK
#     # =========================================================

#     def fetchCommandVelocityCallback(self, msg):

#         self.last_time_cmd_vel = self.get_clock().now()

#         self.goal_linear_velocity_x = msg.twist.linear.x
#         self.goal_linear_velocity_y = msg.twist.linear.y
#         self.goal_angular_velocity_z = msg.twist.angular.z

#     # =========================================================
#     # INVERSE KINEMATICS
#     # =========================================================

#     def calculateInverseKinematics(self):

#         # Robot velocity
#         linear_velocity = self.goal_linear_velocity_x
#         angular_velocity = self.goal_angular_velocity_z

#         # -----------------------------------------------------
#         # Differential drive equations
#         #
#         # Left wheel:
#         # v_left = v - (omega * L / 2)
#         #
#         # Right wheel:
#         # v_right = v + (omega * L / 2)
#         # -----------------------------------------------------

#         left_velocity = (
#             linear_velocity
#             - (angular_velocity * self.wheel_seperation / 2.0)
#         )

#         right_velocity = (
#             linear_velocity
#             + (angular_velocity * self.wheel_seperation / 2.0)
#         )

#         # -----------------------------------------------------
#         # Convert m/s -> RPM
#         # -----------------------------------------------------

#         left_rpm = left_velocity * self.mps_to_rpm
#         right_rpm = right_velocity * self.mps_to_rpm

#         # -----------------------------------------------------
#         # Assign wheel speeds
#         #
#         # [FLEFT, FRIGHT, RLEFT, RRIGHT]
#         # [  0,     1,     2,     3 ]
#         # -----------------------------------------------------

#         self.wheel_speed_cmd[self.FLEFT] = left_rpm
#         self.wheel_speed_cmd[self.FRIGHT] = right_rpm
#         self.wheel_speed_cmd[self.RLEFT] = left_rpm
#         self.wheel_speed_cmd[self.RRIGHT] = right_rpm

#         # Put wheel speeds into ROS message
#         self.motor_speed.speed = self.wheel_speed_cmd

#     # =========================================================
#     # UPDATE CALLBACK
#     # =========================================================

#     def update_callback(self):

#         time_now = self.get_clock().now()

#         # -----------------------------------------------------
#         # Safety timeout
#         #
#         # If no cmd_vel is received for more than 1 second,
#         # stop all motors.
#         # -----------------------------------------------------

#         time_since_cmd = (
#             time_now - self.last_time_cmd_vel
#         ).nanoseconds / 1e9

#         if time_since_cmd > 1.0:

#             self.goal_linear_velocity_x = 0.0
#             self.goal_linear_velocity_y = 0.0
#             self.goal_angular_velocity_z = 0.0

#         # Calculate wheel speeds
#         self.calculateInverseKinematics()

#         # Publish motor command
#         self.speed_control_pub.publish(
#             self.motor_speed
#         )


# # =============================================================
# # MAIN
# # =============================================================

# def main(args=None):

#     rclpy.init(args=args)

#     inverse_kinematics = INVERSEKINEMATICS()

#     rclpy.spin(inverse_kinematics)

#     inverse_kinematics.destroy_node()

#     rclpy.shutdown()


# if __name__ == '__main__':
#     main()

#!/usr/bin/env python3
import rclpy
from rclpy.node import Node

from geometry_msgs.msg import TwistStamped
from ired_msgs.msg import MotorSpeed

class INVERSEKINEMATICS(Node):
    def __init__(self):
        super().__init__('inverse_kinematics_node')
        
        # Initialise Variables and Parameters
        self.initial_parameters()
        self.initial_variables()
        
        # Initialise ROS Publisher and Subscriber
        self.speed_control_pub = self.create_publisher(MotorSpeed, self.inverse_kinematics_topic, 10)
        self.create_subscription(TwistStamped, self.cmd_vel_topic, self.fetchCommandVelocityCallback, 10)
        
        # Initialise ROS Timers
        timer_period = 0.1 # seconds
        self.timer = self.create_timer(timer_period, self.update_callback)
        
        # ROS Logger
        self.get_logger().info(f"Inverse : ROS publisher on {self.inverse_kinematics_topic} [ired_msgs/MotorSpeed]")
        self.get_logger().info(f"Inverse : ROS subscriber on {self.cmd_vel_topic} [geometry_msgs/TwistStamped]")
    
    def initial_parameters(self):
        # Declare parameters
        self.declare_parameter('cmd_vel_topic', '/cmd_vel')
        self.declare_parameter('motor_control_topic', '/ired/motor/speed_control')
        self.declare_parameter('wheel_seperation', 0.199)
        self.declare_parameter('mps_to_rpm', 280.8616642798)
        
        # ROS Parameters
        self.cmd_vel_topic = self.get_parameter('cmd_vel_topic').get_parameter_value().string_value
        self.inverse_kinematics_topic = self.get_parameter('motor_control_topic').get_parameter_value().string_value
        self.wheel_seperation = self.get_parameter('wheel_seperation').get_parameter_value().double_value
        self.mps_to_rpm = self.get_parameter('mps_to_rpm').get_parameter_value().double_value

        self.last_time_speed_fb = self.get_clock().now()
    
    def initial_variables(self):
        self.goal_linear_velocity_x = 0.0
        self.goal_linear_velocity_y = 0.0
        self.goal_angular_velocity_z = 0.0
        self.wheel_speed_cmd = [0.0, 0.0, 0.0, 0.0]
        self.motor_speed = MotorSpeed()
        self.motor_speed.speed = [0.0, 0.0, 0.0, 0.0]
        self.FLEFT = 0
        self.FRIGHT = 1
        self.RLEFT = 2
        self.RRIGHT = 3
        self.last_time_cmd_vel = self.get_clock().now()
        
    def fetchCommandVelocityCallback(self, msg):
        self.last_time_cmd_vel = self.get_clock().now()
        
        self.goal_linear_velocity_x = msg.twist.linear.x
        self.goal_linear_velocity_y = msg.twist.linear.y
        self.goal_angular_velocity_z = msg.twist.angular.z
        
    # def calculateInverseKinematics(self):
    #     # Edit code here
    #     pass
    def calculateInverseKinematics(self):
        vx = self.goal_linear_velocity_x
        vy = self.goal_linear_velocity_y
        omega = self.goal_angular_velocity_z

        R = self.wheel_seperation / 2.0

        # sqrt(2) / 2
        k = 0.7071067811865476

        # ---------------------------------------------------------
        # Wheel velocity
        #
        # [FLEFT, FRIGHT, RLEFT, RRIGHT]
        # [ 45°,   315°,    135°,   225°]
        # ---------------------------------------------------------

        # front_left_velocity = -1.0 * (
        #     vx * k +
        #     vy * k +
        #     omega * R
        # )

        # front_right_velocity = -1.0 * (
        #     vx * (-k) +
        #     vy * k +
        #     omega * R
        # )

        # rear_left_velocity = -1.0 * (
        #     vx * k +
        #     vy * (-k) +
        #     omega * R
        # )

        # rear_right_velocity = -1.0 * (
        #     vx * (-k) +
        #     vy * (-k) +
        #     omega * R
        # )

        front_left_velocity = -1.0 * (
            vx * k +
            vy * k -
            omega * R
        )

        front_right_velocity = -1.0 * (
            vx * (-k) +
            vy * k -
            omega * R
        )

        rear_left_velocity = -1.0 * (
            vx * k +
            vy * (-k) -
            omega * R
        )

        rear_right_velocity = -1.0 * (
            vx * (-k) +
            vy * (-k) -
            omega * R
        )

        # ---------------------------------------------------------
        # Convert m/s -> RPM
        # ---------------------------------------------------------

        self.wheel_speed_cmd[self.FLEFT] = (
            front_left_velocity * self.mps_to_rpm
        )

        self.wheel_speed_cmd[self.FRIGHT] = (
            front_right_velocity * self.mps_to_rpm
        )

        self.wheel_speed_cmd[self.RLEFT] = (
            rear_left_velocity * self.mps_to_rpm
        )

        self.wheel_speed_cmd[self.RRIGHT] = (
            rear_right_velocity * self.mps_to_rpm
        )

        self.motor_speed.speed = self.wheel_speed_cmd

    def update_callback(self):
        time_now = self.get_clock().now()
        
        if (time_now - self.last_time_cmd_vel).nanoseconds / 1e9 > 1.0:
            self.goal_linear_velocity_x = 0.0
            self.goal_linear_velocity_y = 0.0
            self.goal_angular_velocity_z = 0.0
        
        self.calculateInverseKinematics()
        self.speed_control_pub.publish(self.motor_speed)

def main(args=None):
    rclpy.init(args=args)
    inverse_kinematics = INVERSEKINEMATICS()
    
    rclpy.spin(inverse_kinematics)
    
    inverse_kinematics.destroy_node()
    rclpy.shutdown()
    
if __name__ == '__main__':
    main()