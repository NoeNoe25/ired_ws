#!/usr/bin/env python3
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseWithCovarianceStamped
from tf_transformations import euler_from_quaternion
import json
import sys
import os
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
import mqtt_interface

from refbox_msgs.msg import NavigationRoutesData, NavigationRoutes, NavigationRoutesPoint
from refbox_msgs.msg import MachineInfoData, MachineInfo
from refbox_msgs.msg import GameInfo, GamePlay
from refbox_msgs.srv import MachineReport


class RefboxNode(Node):
    def __init__(self):
        super().__init__('mqtt_refbox_node')

        # Robot pose
        self.pose_x_ = 0.0
        self.pose_y_ = 0.0
        self.angle_z_ = 0.0

        # MQTT client
        self.mqtt_ = mqtt_interface.RobotMQTTClient()
        self.mqtt_.mqttConnect()

        # ROS2 Publishers
        self.navigation_routes_pub_ = self.create_publisher(NavigationRoutesData, '/refbox/navigation_routes', 10)
        self.machine_info_pub_ = self.create_publisher(MachineInfoData, '/refbox/machine_info', 10)
        self.game_info_pub_ = self.create_publisher(GameInfo, '/refbox/game_info', 10)
        self.game_play_pub_ = self.create_publisher(GamePlay, '/refbox/game_play', 10)

        # ROS2 Subscriber
        self.create_subscription(PoseWithCovarianceStamped, '/amcl_pose', self.robot_position_callback, 10)

        # Service for machine report
        self.srv_machine_report_ = self.create_service(
            MachineReport,
            '/refbox/machine_report',
            self.handle_machine_report_service
        )
        
        # Timer for periodic publishing (1 Hz)
        self.timer = self.create_timer(1.0, self.timer_callback)

        self.get_logger().info("REFBOX Node Initialized")

    # ==================== ROS Subscriber ====================
    def robot_position_callback(self, msg: PoseWithCovarianceStamped):
        pose = msg.pose.pose
        euler_angle = euler_from_quaternion([
            pose.orientation.x,
            pose.orientation.y,
            pose.orientation.z,
            pose.orientation.w
        ])
        self.pose_x_ = pose.position.x
        self.pose_y_ = pose.position.y
        self.angle_z_ = (270.0 - (euler_angle[2] * 180.0 / 3.141592653)) % 360
    
    # ==================== Service Callback ====================
    def handle_machine_report_service(self, request, response):
        """
        ROS2 service callback: call MQTT interface to publish machine report
        """
        try:
            status = self.mqtt_.machine_report_publish(
                request.machine,
                request.x,
                request.y,
                request.yaw
            )
            response.status = status
        except Exception as e:
            self.get_logger().error(f"Failed to publish machine report: {e}")
            response.status = False

        return response

    # ==================== Timer callback ====================
    def timer_callback(self):
        # ----- Game Info -----
        game_state_ = self.mqtt_.latest_game_state_
        game_phase_ = self.mqtt_.latest_phase_
        team_color_ = self.mqtt_.latest_team_color_ or ""

        if game_state_ and game_phase_:
            game_info_msg_, game_play_msg_ = self.game_info_check(game_state_, game_phase_, team_color_)
            self.game_info_pub_.publish(game_info_msg_)
            self.game_play_pub_.publish(game_play_msg_)
        else:
            # Publish empty/default game info if missing
            game_info_msg_ = GameInfo()
            game_info_msg_.team_color = team_color_
            self.game_info_pub_.publish(game_info_msg_)
            game_play_msg_ = GamePlay()
            self.game_play_pub_.publish(game_play_msg_)

        # ----- Navigation Routes -----
        navigation_routes_ = self.mqtt_.latest_navigation_routes_
        if navigation_routes_ and navigation_routes_ != {}:
            route_msg_ = self.parse_route_info(navigation_routes_)
        else:
            route_msg_ = NavigationRoutesData()
            route_msg_.team_color = team_color_
        self.navigation_routes_pub_.publish(route_msg_)

        # ----- Machine Info -----
        machine_info_ = self.mqtt_.latest_machine_info_
        if machine_info_ and machine_info_ != {}:
            machine_info_msg_ = self.parse_machine_info(machine_info_)
        else:
            machine_info_msg_ = MachineInfoData()
            machine_info_msg_.team_color = team_color_
        self.machine_info_pub_.publish(machine_info_msg_)

        # ----- Robot Pose MQTT -----
        self.mqtt_.robot_position_publish(self.pose_x_, self.pose_y_, round(self.angle_z_))

    # ==================== Helper Functions ====================
    def game_info_check(self, game_state, game_phase, team_color):
        game_info_msg_ = GameInfo()
        game_play_msg_ = GamePlay()

        game_info_msg_.team_color = team_color
        game_info_msg_.phase = game_phase
        game_info_msg_.game_state = game_state

        if game_phase == "PRODUCTION" and game_state == "RUNNING":
            game_play_msg_.status = True
        else:
            game_play_msg_.status = False

        return game_info_msg_, game_play_msg_

    def parse_route_info(self, json_data):
        route_data_msg = NavigationRoutesData()
        route_data_msg.team_color = json_data.get("teamColor", "")

        for route in json_data.get("routes", []):
            route_msg = NavigationRoutes()
            route_msg.id = route.get("id", 0)

            for zone in route.get("route", []):
                zone_msg = NavigationRoutesPoint()
                zone_msg.zone = zone
                zone_msg.position.x = float(zone[3])
                zone_msg.position.y = float(zone[4])
                route_msg.route.append(zone_msg)

            for zone in route.get("remaining", []):
                zone_msg = NavigationRoutesPoint()
                zone_msg.zone = zone
                zone_msg.position.x = float(zone[3])
                zone_msg.position.y = float(zone[4])
                route_msg.remaining.append(zone_msg)

            route_data_msg.routes.append(route_msg)

        return route_data_msg

    def parse_machine_info(self, json_data):
        machine_info_msg = MachineInfoData()
        machine_info_msg.team_color = json_data.get("teamColor", "")

        for machine in json_data.get("machines", []):
            machine_msg = MachineInfo()
            machine_msg.name = machine.get("name", "")
            machine_msg.type = machine.get("type", "")
            machine_msg.state = machine.get("state", "")
            machine_msg.team_color = machine.get("teamColor", "")
            machine_msg.zone = machine.get("zone", "")
            machine_msg.rotation = machine.get("rotation", 0)
            machine_info_msg.machines.append(machine_msg)

        return machine_info_msg


def main(args=None):
    rclpy.init(args=args)
    node = RefboxNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.mqtt_.mqttDisconnect()
        node.destroy_node()
        rclpy.shutdown()


if __name__ == "__main__":
    main()
