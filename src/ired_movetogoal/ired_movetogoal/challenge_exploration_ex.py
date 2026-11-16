#!/usr/bin/env python3
"""Exploration Challenge: search the field for the 2 machines with Nav2.

Plan:
  - Drive a snake path over the field (WAYPOINTS, zone centres).
  - At every waypoint turn 360 deg in 90 deg steps, stopping SCAN_PAUSE s after each step
    so the camera gets sharp frames.
  - When the camera sees a machine that is not reported yet -> stop and hold still
    (HOLD_TIME s) so aruco_report_node can confirm and send it.
  - Stop when both machines are reported (/aruco/reported), or the waypoints run out.
  - Only moves while the RefBox game is RUNNING in the EXPLORATION phase (MQTT 1883).

Needs running: bringup, navigation, aruco.launch.py (detect + pose_zone + report).
Set the start pose with 2D Pose Estimate in RViz BEFORE starting this node.
"""
import json
import math
import threading
import time

import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from std_msgs.msg import String
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult

# Snake path over the inner zones (zone centres). Zones with a box in them fail -> skipped.
WAYPOINTS = [
    (3.5, 1.5), (2.5, 1.5), (1.5, 1.5),
    (1.5, 2.5), (2.5, 2.5), (3.5, 2.5),
    (3.5, 3.5), (2.5, 3.5), (1.5, 3.5),
    (1.5, 4.5), (2.5, 4.5), (3.5, 4.5),
]
MACHINES = {'CS1', 'BS'}
SCAN_PAUSE = 1.5     # s still after each 90 deg turn
HOLD_TIME = 3.0      # s still when a new machine is in view
# PHASE = 'EXPLORATION'
PHASE = 'PRODUCTION'

def new_client():
    try:  # paho-mqtt 2.x
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:  # paho-mqtt 1.x
        return mqtt.Client()


class ExplorationChallenge(Node):
    def __init__(self):
        super().__init__('exploration_challenge_node')
        P = self.declare_parameter
        broker = P('broker', '172.16.0.245').value
        robot_ip = P('robot_ip', '172.16.0.24').value

        self.lock = threading.Lock()
        self.game = {'state': None, 'phase': None}
        self.visible = {}          # machine -> last time seen
        self.reported = set()
        self.next_wp = 0
        self.running = False
        self.finished = False

        # ---- game state from the bridge (same as the bridge example script) ----
        def on_msg(client, userdata, msg):
            text = msg.payload.decode(errors='replace').strip().strip('"').upper()
            with self.lock:
                if msg.topic.endswith('/game_state'):
                    self.game['state'] = text
                elif msg.topic.endswith('/phase'):
                    self.game['phase'] = text

        self.mqtt = new_client()
        self.mqtt.on_message = on_msg
        self.mqtt.connect(broker, 1883)
        self.mqtt.subscribe(f'{robot_ip}/game_state')
        self.mqtt.subscribe(f'{robot_ip}/phase')
        self.mqtt.loop_start()

        # ---- ROS ----
        self.create_subscription(String, '/aruco/detections', self.on_detections, 10)
        self.create_subscription(String, '/aruco/reported', self.on_reported, 10)
        self.create_timer(0.5, self.update)

        self.nav = BasicNavigator()
        # don't publish a (0,0) initial pose - keep the one set in RViz
        self.nav.waitUntilNav2Active(localizer='robot_localization')
        self.get_logger().info('Exploration ready: waiting for RUNNING + EXPLORATION')

    # ---------------- callbacks ----------------
    def on_detections(self, msg):
        try:
            markers = json.loads(msg.data).get('markers', [])
        except json.JSONDecodeError:
            return
        now = time.time()
        with self.lock:
            for m in markers:
                if m.get('machine') in MACHINES:
                    self.visible[m['machine']] = now

    def on_reported(self, msg):
        try:
            with self.lock:
                self.reported = set(json.loads(msg.data))
        except (json.JSONDecodeError, TypeError):
            pass

    def game_on(self):
        with self.lock:
            s, ph = self.game['state'], self.game['phase']
        return s is not None and 'RUNNING' in s and ph is not None and PHASE in ph

    def all_reported(self):
        with self.lock:
            return MACHINES <= self.reported

    def new_machine_in_view(self):
        now = time.time()
        with self.lock:
            return any(now - t < 0.5 and m not in self.reported for m, t in self.visible.items())

    def update(self):
        if self.running or self.finished:
            return
        if self.game_on():
            self.running = True
            self.get_logger().info('Game RUNNING (EXPLORATION) -> exploring')
            threading.Thread(target=self.explore, daemon=True).start()

    # ---------------- motion ----------------
    def make_pose(self, x, y, yaw):
        p = PoseStamped()
        p.header.frame_id = 'map'
        p.header.stamp = self.nav.get_clock().now().to_msg()
        p.pose.position.x, p.pose.position.y = x, y
        p.pose.orientation.z = math.sin(yaw / 2)
        p.pose.orientation.w = math.cos(yaw / 2)
        return p

    def wait_task(self, stop_on_machine):
        """Wait for the Nav2 task. Returns 'ok', 'failed', 'paused' or 'machine'."""
        while rclpy.ok():
            if not self.game_on():
                self.nav.cancelTask()
                return 'paused'
            if stop_on_machine and self.new_machine_in_view():
                self.nav.cancelTask()
                return 'machine'
            if self.nav.isTaskComplete():
                break
            time.sleep(0.1)
        return 'ok' if self.nav.getResult() == TaskResult.SUCCEEDED else 'failed'

    def hold(self, seconds):
        """Stand still. Returns False if paused or both machines are done."""
        end = time.time() + seconds
        while time.time() < end:
            if not self.game_on() or self.all_reported():
                return False
            time.sleep(0.1)
        return True

    def hold_for_machine(self):
        self.get_logger().info('New machine in view -> holding still for the report')
        self.hold(HOLD_TIME)
        with self.lock:
            self.get_logger().info(f'Reported so far: {sorted(self.reported)}')

    def go_to(self, x, y):
        self.nav.clearAllCostmaps()
        if not self.nav.goToPose(self.make_pose(x, y, 0.0)):
            return 'failed'
        return self.wait_task(stop_on_machine=True)

    def scan_here(self):
        """Turn 360 deg in 4 steps, pausing after each. Returns False if paused / done."""
        for _ in range(4):
            if not self.hold(SCAN_PAUSE):
                return False
            if self.new_machine_in_view():
                self.hold_for_machine()
            if self.all_reported():
                return False
            if not self.nav.spin(spin_dist=math.pi / 2, time_allowance=10):
                continue
            res = self.wait_task(stop_on_machine=True)
            if res == 'paused':
                return False
            if res == 'machine':
                self.hold_for_machine()
        return True

    def explore(self):
        try:
            while self.next_wp < len(WAYPOINTS) and rclpy.ok():
                if self.all_reported():
                    break
                x, y = WAYPOINTS[self.next_wp]
                self.get_logger().info(f'-> waypoint {self.next_wp + 1}/{len(WAYPOINTS)} ({x}, {y})')
                res = self.go_to(x, y)
                if res == 'paused':
                    return                       # resume this waypoint later
                if res == 'machine':
                    self.hold_for_machine()
                    if self.all_reported():
                        break
                    res = self.go_to(x, y)        # continue to the waypoint
                    if res == 'paused':
                        return
                if res == 'failed':
                    self.get_logger().warn('   waypoint not reachable (box there?) -> skip')
                    self.next_wp += 1
                    continue
                if not self.scan_here() and not self.all_reported():
                    return                       # paused
                self.next_wp += 1

            if self.all_reported():
                self.get_logger().info('BOTH MACHINES REPORTED - exploration done')
            else:
                with self.lock:
                    self.get_logger().warn(f'Waypoints finished, reported: {sorted(self.reported)}')
            self.finished = True
        finally:
            self.running = False

    def close(self):
        self.mqtt.loop_stop()
        self.mqtt.disconnect()


def main():
    rclpy.init()
    node = ExplorationChallenge()
    from rclpy.executors import MultiThreadedExecutor
    ex = MultiThreadedExecutor(num_threads=4)
    ex.add_node(node)          # navigator spins itself inside its calls
    try:
        ex.spin()
    except KeyboardInterrupt:
        pass
    finally:
        ex.shutdown()
        node.close()
        node.destroy_node()
        node.nav.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()