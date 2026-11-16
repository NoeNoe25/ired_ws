# #!/usr/bin/env python3
# """Send ArUco machine reports to the RefBox (MQTT): machine type, zone, box angle.

# Inputs (ROS):
#   /aruco/detections  {"markers": [{"id": 101, "machine": "CS1", "side": "output", "marker_yaw": -12.3}]}
#   /pose_zone         {"x": 4.5, "y": 0.5, "zone": "C_Z51", "robot_yaw_deg": 180.0, "box_angle": 0}

# Output (MQTT, bridge format - exactly these 4 keys):
#   TEAM_CYAN/report   {"machine": "C-CS1", "x": 4.5, "y": 0.5, "yaw": 0}
#      machine = team letter + machine type, x/y = centre of the zone, yaw = box angle
#   The bridge turns x/y into the zone name (C_Z51).

# Also publishes /aruco/reported (std_msgs/String) ["BS", "CS1"] for the exploration script.

# Each machine is reported ONCE, after its marker is seen in `confirm` messages in a row,
# and only while the game is RUNNING (EXPLORATION or PRODUCTION). Logs every 3 s.
# """
# import json
# import time

# import paho.mqtt.client as mqtt
# import rclpy
# from rclpy.node import Node
# from std_msgs.msg import String

# TEAM_PORT = {'CYAN': 21883, 'MAGENTA': 11883}
# LOG_PERIOD = 3.0


# def new_client():
#     try:  # paho-mqtt 2.x
#         return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
#     except AttributeError:  # paho-mqtt 1.x
#         return mqtt.Client()


# def zone_centre(zone):
#     """'C_Z51' -> (4.5, 0.5); 'M_Z51' -> (-4.5, 0.5)."""
#     col, row = int(zone[-2]), int(zone[-1])
#     x = col - 0.5
#     return (-x if zone.startswith('M') else x), row - 0.5


# class ArucoReportNode(Node):
#     def __init__(self):
#         super().__init__('aruco_report_node')
#         P = self.declare_parameter
#         broker = P('broker', '172.16.0.245').value
#         robot_ip = P('robot_ip', '172.16.0.24').value
#         team = str(P('team', 'CYAN').value).upper()
#         self.confirm = int(P('confirm', 5).value)
#         self.dry_run = bool(P('dry_run', False).value)

#         self.team = team
#         self.topic = f'TEAM_{team}/report'
#         self.pose = None
#         self.game = {'state': None, 'phase': None}
#         self.count = {}          # machine -> consecutive sightings
#         self.reported = set()    # machines already reported
#         self.last_log = 0.0

#         # ---- MQTT: game state (1883) + team broker for reports ----
#         robot = robot_ip

#         def on_msg(client, userdata, msg):
#             text = msg.payload.decode(errors='replace').strip().strip('"').upper()
#             if msg.topic.endswith('/game_state'):
#                 self.game['state'] = text
#             elif msg.topic.endswith('/phase'):
#                 self.game['phase'] = text

#         self.state_client = new_client()
#         self.state_client.on_message = on_msg
#         self.state_client.connect(broker, 1883)
#         self.state_client.subscribe(f'{robot}/game_state')
#         self.state_client.subscribe(f'{robot}/phase')
#         self.state_client.loop_start()

#         self.report_client = new_client()
#         self.report_client.connect(broker, TEAM_PORT[team])
#         self.report_client.loop_start()

#         # ---- ROS ----
#         self.create_subscription(String, '/pose_zone', self.on_pose, 10)
#         self.create_subscription(String, '/aruco/detections', self.on_detections, 10)
#         self.reported_pub = self.create_publisher(String, '/aruco/reported', 10)
#         self.create_timer(LOG_PERIOD, self.log)

#         self.get_logger().info(f'Reporting to {broker}:{TEAM_PORT[team]} topic {self.topic}'
#                                + ('  (DRY RUN)' if self.dry_run else ''))

#     def game_allows(self):
#         s, ph = self.game['state'], self.game['phase']
#         if s is None and ph is None:
#             return True                          # bridge never told us -> allow
#         return (s is None or 'RUNNING' in s) and \
#                (ph is None or 'EXPLORATION' in ph or 'PRODUCTION' in ph)

#     def on_pose(self, msg):
#         try:
#             self.pose = json.loads(msg.data)
#         except json.JSONDecodeError:
#             pass

#     def on_detections(self, msg):
#         if self.pose is None or self.pose.get('zone', '').startswith('Outside'):
#             return
#         try:
#             markers = json.loads(msg.data).get('markers', [])
#         except json.JSONDecodeError:
#             return
#         seen = {m['machine'] for m in markers if m.get('machine') not in (None, '?')}
#         for machine in list(self.count):
#             if machine not in seen:
#                 self.count[machine] = 0          # lost -> start counting again
#         for machine in seen:
#             if machine in self.reported:
#                 continue
#             self.count[machine] = self.count.get(machine, 0) + 1
#             if self.count[machine] < self.confirm or not self.game_allows():
#                 continue
#             self.send(machine)

#     def send(self, machine):
#         zone = self.pose['zone']
#         x, y = zone_centre(zone)
#         payload = json.dumps({'machine': f'{self.team[0]}-{machine}',
#                               'x': x, 'y': y, 'yaw': int(self.pose['box_angle'])})
#         if not self.dry_run:
#             self.report_client.publish(self.topic, payload)
#         self.reported.add(machine)
#         self.reported_pub.publish(String(data=json.dumps(sorted(self.reported))))
#         self.get_logger().info(f'REPORT {payload}  ({zone})'
#                                + ('  DRY RUN, not sent' if self.dry_run else ''))

#     def log(self):
#         z = self.pose.get('zone') if self.pose else None
#         a = self.pose.get('box_angle') if self.pose else None
#         self.get_logger().info(f'zone={z} box_angle={a} game={self.game["state"]}/'
#                                f'{self.game["phase"]} reported={sorted(self.reported)}')

#     def close(self):
#         for c in (self.state_client, self.report_client):
#             c.loop_stop()
#             c.disconnect()


# def main():
#     rclpy.init()
#     node = ArucoReportNode()
#     try:
#         rclpy.spin(node)
#     except KeyboardInterrupt:
#         pass
#     finally:
#         node.close()
#         node.destroy_node()
#         if rclpy.ok():
#             rclpy.shutdown()


# if __name__ == '__main__':
#     main()



#!/usr/bin/env python3
"""Send ArUco machine reports to the RefBox (MQTT): machine type, MACHINE zone, box angle.

Inputs (ROS):
  /aruco/detections  {"markers": [{"id": 101, "machine": "CS1", "side": "output",
                                   "marker_yaw": -12.3, "x": -0.05, "z": 0.62}]}
                     x = marker right of camera (m), z = marker in front of camera (m)
  /pose_zone         {"x": 2.5, "y": 1.5, "zone": "C_Z32", "robot_yaw_deg": 90.0, "box_angle": 0}

Machine position = robot pose + marker position from the camera, pushed BOX_HALF
further (marker is on the box side, centre is 10 cm behind it). Its zone is reported.

Output (MQTT, bridge format - exactly these 4 keys), QoS 1 with retry:
  TEAM_CYAN/report   {"machine": "C-CS1", "x": 2.5, "y": 2.5, "yaw": 0}
Also publishes /aruco/reported (std_msgs/String) ["BS", "CS1"] for the exploration script.

Each machine is reported once, after `confirm` sightings within ~1 s gaps, only while
the game is RUNNING (EXPLORATION or PRODUCTION). Logs every 3 s, including WHY it is waiting.
"""
import json
import math
import time
from math import floor

import paho.mqtt.client as mqtt
import rclpy
from rclpy.node import Node
from std_msgs.msg import String

TEAM_PORT = {'CYAN': 21883, 'MAGENTA': 11883}
LOG_PERIOD = 3.0
BOX_HALF = 0.10       # marker -> machine centre (box is 20 x 20 cm)
GAP_RESET = 1.0       # s without the marker -> start counting again


def new_client():
    try:  # paho-mqtt 2.x
        return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
    except AttributeError:  # paho-mqtt 1.x
        return mqtt.Client()


def zone_of(x, y):
    col, row = floor(abs(x)), floor(y)
    if not (0 <= col < 5 and 0 <= row < 5):
        return None
    return f"{'C' if x >= 0 else 'M'}_Z{col + 1}{row + 1}"


def zone_centre(zone):
    """'C_Z51' -> (4.5, 0.5); 'M_Z51' -> (-4.5, 0.5)."""
    col, row = int(zone[-2]), int(zone[-1])
    x = col - 0.5
    return (-x if zone.startswith('M') else x), row - 0.5


def machine_xy(rx, ry, ryaw_deg, cam_x, cam_z, cam_forward):
    """Robot pose (map) + marker in camera frame -> machine centre (map)."""
    th = math.radians(ryaw_deg)
    fwd = cam_z + cam_forward            # metres in front of the robot centre
    left = -cam_x                        # camera x is to the right
    d = math.hypot(fwd, left)
    if d > 1e-6:                         # push BOX_HALF further along the view ray
        fwd += BOX_HALF * fwd / d
        left += BOX_HALF * left / d
    mx = rx + fwd * math.cos(th) - left * math.sin(th)
    my = ry + fwd * math.sin(th) + left * math.cos(th)
    return mx, my


class ArucoReportNode(Node):
    def __init__(self):
        super().__init__('aruco_report_node')
        P = self.declare_parameter
        broker = P('broker', '172.16.0.245').value
        robot_ip = P('robot_ip', '172.16.0.24').value
        team = str(P('team', 'CYAN').value).upper()
        self.confirm = int(P('confirm', 5).value)
        self.dry_run = bool(P('dry_run', False).value)
        self.cam_forward = float(P('cam_forward', 0.0).value)   # camera in front of robot centre (m)

        self.team = team
        self.topic = f'TEAM_{team}/report'
        self.pose = None
        self.pose_t = 0.0
        self.game = {'state': None, 'phase': None}
        self.hist = {}           # machine -> list of (x, y, angle)
        self.last_seen = {}      # machine -> time
        self.reported = set()
        self.status = 'waiting for /pose_zone and /aruco/detections'

        # ---- MQTT: game state (1883) + team broker for reports ----
        def on_msg(client, userdata, msg):
            text = msg.payload.decode(errors='replace').strip().strip('"').upper()
            if msg.topic.endswith('/game_state'):
                self.game['state'] = text
            elif msg.topic.endswith('/phase'):
                self.game['phase'] = text

        self.state_client = new_client()
        self.state_client.on_message = on_msg
        self.state_client.connect(broker, 1883)
        self.state_client.subscribe(f'{robot_ip}/game_state')
        self.state_client.subscribe(f'{robot_ip}/phase')
        self.state_client.loop_start()

        self.report_client = new_client()
        self.report_client.connect(broker, TEAM_PORT[team])
        self.report_client.loop_start()

        # ---- ROS ----
        self.create_subscription(String, '/pose_zone', self.on_pose, 10)
        self.create_subscription(String, '/aruco/detections', self.on_detections, 10)
        self.reported_pub = self.create_publisher(String, '/aruco/reported', 10)
        self.create_timer(LOG_PERIOD, self.log)

        self.get_logger().info(f'Reporting to {broker}:{TEAM_PORT[team]} topic {self.topic}'
                               + ('  (DRY RUN)' if self.dry_run else ''))

    def game_allows(self):
        s, ph = self.game['state'], self.game['phase']
        if s is None and ph is None:
            return True                          # bridge never told us -> allow
        return (s is None or 'RUNNING' in s) and \
               (ph is None or 'EXPLORATION' in ph or 'PRODUCTION' in ph)

    def on_pose(self, msg):
        try:
            self.pose = json.loads(msg.data)
            self.pose_t = time.time()
        except json.JSONDecodeError:
            pass

    def on_detections(self, msg):
        now = time.time()
        if self.pose is None or now - self.pose_t > 2.0:
            self.status = 'BLOCKED: no fresh /pose_zone'
            return
        try:
            markers = json.loads(msg.data).get('markers', [])
        except json.JSONDecodeError:
            return
        rx, ry = float(self.pose.get('x', 0)), float(self.pose.get('y', 0))
        ryaw = float(self.pose.get('robot_yaw_deg', 0))
        angle = int(self.pose.get('box_angle', 0))

        for m in markers:
            machine = m.get('machine')
            if machine in (None, '?') or machine in self.reported:
                continue
            if 'x' not in m or 'z' not in m:
                self.status = 'BLOCKED: /aruco/detections has no x/z (update aruco_detect)'
                continue
            mx, my = machine_xy(rx, ry, ryaw, float(m['x']), float(m['z']), self.cam_forward)
            if zone_of(mx, my) is None:
                self.status = (f'BLOCKED: {machine} at ({mx:.2f}, {my:.2f}) is outside the field '
                               f'- robot pose ({rx:.2f}, {ry:.2f}) wrong?')
                continue
            if now - self.last_seen.get(machine, 0) > GAP_RESET:
                self.hist[machine] = []
            self.last_seen[machine] = now
            self.hist[machine].append((mx, my, angle))
            n = len(self.hist[machine])
            if n < self.confirm:
                self.status = f'{machine}: {n}/{self.confirm} sightings'
                continue
            if not self.game_allows():
                self.status = f'{machine} ready, but game is {self.game["state"]}/{self.game["phase"]}'
                continue
            self.send(machine)

    def send(self, machine):
        h = self.hist[machine][-self.confirm:]
        mx = sum(p[0] for p in h) / len(h)
        my = sum(p[1] for p in h) / len(h)
        angle = max(set(p[2] for p in h), key=[p[2] for p in h].count)   # most common
        zone = zone_of(mx, my)
        x, y = zone_centre(zone)
        payload = json.dumps({'machine': f'{self.team[0]}-{machine}',
                              'x': x, 'y': y, 'yaw': angle})
        if self.dry_run:
            ok = True
        else:
            ok = False
            for _ in range(3):                                   # QoS 1 + retry
                info = self.report_client.publish(self.topic, payload, qos=1)
                try:
                    info.wait_for_publish(timeout=2.0)
                except (RuntimeError, ValueError):
                    pass
                if info.is_published():
                    ok = True
                    break
        if not ok:
            self.status = f'SEND FAILED for {machine}, will retry on next sighting'
            self.get_logger().error(self.status)
            self.hist[machine] = []
            return
        self.reported.add(machine)
        self.reported_pub.publish(String(data=json.dumps(sorted(self.reported))))
        self.status = f'reported {machine}'
        self.get_logger().info(f'REPORT {payload}  (machine at {mx:.2f}, {my:.2f} -> {zone})'
                               + ('  DRY RUN, not sent' if self.dry_run else ''))

    def log(self):
        p = self.pose or {}
        self.get_logger().info(f'robot zone={p.get("zone")} box_angle={p.get("box_angle")} '
                               f'game={self.game["state"]}/{self.game["phase"]} '
                               f'reported={sorted(self.reported)} | {self.status}')

    def close(self):
        for c in (self.state_client, self.report_client):
            c.loop_stop()
            c.disconnect()


def main():
    rclpy.init()
    node = ArucoReportNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.close()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()


if __name__ == '__main__':
    main()