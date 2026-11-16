# #!/usr/bin/env python3
# """ArUco machine-marker detector as a ROS 2 node.
# RefBox logic is the SAME as the standalone aruco_detect.py that already works:
# pose, team colour, game state and reports all go over MQTT to the bridge.

# ROS topics (images only drawn/encoded while something subscribes):
#   /aruco/image_view             sensor_msgs/Image            camera view with detections drawn
#   /aruco/image_view/compressed  sensor_msgs/CompressedImage  same, JPEG
#   /aruco/report                 std_msgs/String  {"machine": "C-BS", "x": 2.5, "y": 3.5, "yaw": 225}
#                                 sent ONCE per marker, after it is seen stable for `confirm` frames
#   /aruco/detections             std_msgs/String  every frame, all markers currently seen:
#                                 {"stamp": 1700000000.12, "markers": [{"id": 121, "machine": "BS",
#                                  "side": "output", "dist": 1.23, "bearing": -4.5, "marker_yaw": 12.0,
#                                  "x": -0.1, "z": 1.22}]}   (x right, z forward of camera, metres/deg)

# MQTT layout (Bridge VM, default 172.16.0.245):
#   port 1883            <robot_ip>/teamColor, /pose, /game_state, /phase   (read)
#   port 21883 (CYAN)    TEAM_CYAN/report                                    (write)
#   port 11883 (MAGENTA) TEAM_MAGENTA/report                                 (write)

# Run:   ros2 launch ired_aruco aruco.launch.py team:=CYAN
#        ros2 run ired_aruco aruco_detect --ros-args -p team:=CYAN -p dry_run:=true
# Echo:  ros2 topic echo /aruco/detections
# """
# import glob
# import json
# import os
# import time

# import cv2
# import numpy as np
# import yaml

# import rclpy
# from rclpy.node import Node
# from sensor_msgs.msg import CompressedImage, Image
# from std_msgs.msg import String

# # Marker ID -> (machine, side), from the challenge rules
# MACHINES = {
#     102: ('CS1', 'input'),
#     101: ('CS1', 'output'),
#     122: ('BS', 'input'),
#     121: ('BS', 'output'),
# }
# TEAM_PORT = {'CYAN': 21883, 'MAGENTA': 11883}  # team brokers on the Bridge VM


# def new_client():
#     import paho.mqtt.client as mqtt
#     try:  # paho-mqtt 2.x needs the callback API version
#         return mqtt.Client(mqtt.CallbackAPIVersion.VERSION2)
#     except AttributeError:  # paho-mqtt 1.x
#         return mqtt.Client()


# def zone_name(x, y):
#     """Field zone like C_Z54 (1 m zones, cyan = positive x). For comparing with the website."""
#     side = 'C' if x >= 0 else 'M'
#     return f'{side}_Z{int(abs(x)) + 1}{int(y) + 1}'


# class ArucoNode(Node):
#     def __init__(self):
#         super().__init__('aruco_detect')
#         # ---- parameters (same options as the standalone script) ----
#         P = self.declare_parameter
#         self.size = float(P('size', 0.10).value)
#         team = str(P('team', '').value).upper()            # '' = take colour from the refbox
#         calib = P('calib', os.path.expanduser('~/.ros/camera_info/default_cam.yaml')).value
#         device = P('device', '').value
#         self.fps = float(P('fps', 10.0).value)
#         threads = int(P('threads', 1).value)
#         self.refbox = bool(P('refbox', True).value)
#         self.dry_run = bool(P('dry_run', False).value)
#         refbox_ip = P('refbox_ip', os.environ.get('REFBOX_BRIDGE_ADDRESS', '172.16.0.245')).value
#         robot_ip = P('robot_ip', os.environ.get('ROBOT_IP', '172.16.0.24')).value
#         self.cam_forward = float(P('cam_forward', 0.0).value)
#         self.cam_left = float(P('cam_left', 0.0).value)
#         self.center_offset = float(P('center_offset', 0.35).value)
#         self.yaw_offset = float(P('yaw_offset', 0.0).value)
#         self.confirm = int(P('confirm', 5).value)
#         self.no_pose = bool(P('no_pose', False).value)

#         cv2.setNumThreads(threads)

#         with open(calib) as f:
#             cal = yaml.safe_load(f)
#         self.K = np.array(cal['camera_matrix']['data'], dtype=np.float64).reshape(3, 3)
#         self.D = np.array(cal['distortion_coefficients']['data'], dtype=np.float64)

#         # ArUco detector: works with both old (<4.7) and new OpenCV APIs
#         aruco = cv2.aruco
#         dictionary = aruco.getPredefinedDictionary(aruco.DICT_ARUCO_ORIGINAL)
#         params = aruco.DetectorParameters() if hasattr(aruco, 'ArucoDetector') \
#             else aruco.DetectorParameters_create()
#         params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
#         if hasattr(aruco, 'ArucoDetector'):
#             det = aruco.ArucoDetector(dictionary, params)
#             self.find_markers = det.detectMarkers
#         else:
#             self.find_markers = lambda g: aruco.detectMarkers(g, dictionary, parameters=params)
#         s = self.size / 2
#         # marker corners in marker frame, same order as detectMarkers (TL, TR, BR, BL)
#         self.obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], dtype=np.float64)

#         # ---- ROS publishers ----
#         self.img_pub = self.create_publisher(Image, '/aruco/image_view', 1)
#         self.cimg_pub = self.create_publisher(CompressedImage, '/aruco/image_view/compressed', 1)
#         self.report_pub = self.create_publisher(String, '/aruco/report', 10)
#         self.det_pub = self.create_publisher(String, '/aruco/detections', 10)

#         # ---------------- Refbox (MQTT) - same as standalone ----------------
#         self.team = {'color': team or None}
#         self.robot = {'x': 0.0, 'y': 0.0, 'yaw': 0.0, 't': 0.0}  # latest pose from the bridge
#         self.game = {'state': None, 'phase': None}
#         self.state_client = self.report_client = None
#         self.report_topic = None

#         if self.refbox:
#             def on_message(client, userdata, msg):
#                 text = msg.payload.decode(errors='replace').strip().strip('"')
#                 topic = msg.topic
#                 if topic.endswith('/teamColor'):
#                     if not team:
#                         c = text.upper().replace('TEAM_', '')
#                         self.team['color'] = c or None
#                 elif topic.endswith('/pose'):
#                     try:
#                         d = json.loads(msg.payload)
#                         x, y, yw = float(d['x']), float(d['y']), float(d['yaw'])
#                         if x == 0 and y == 0 and yw == 0:
#                             return  # not localized yet
#                         self.robot.update(x=x, y=y, yaw=yw, t=time.time())
#                     except (ValueError, KeyError, TypeError):
#                         pass
#                 elif topic.endswith('/game_state'):
#                     if self.game['state'] != text.upper():
#                         self.get_logger().info(f'game_state: {text}')
#                     self.game['state'] = text.upper()
#                 elif topic.endswith('/phase'):
#                     if self.game['phase'] != text.upper():
#                         self.get_logger().info(f'phase: {text}')
#                     self.game['phase'] = text.upper()

#             self.state_client = new_client()
#             self.state_client.on_message = on_message
#             self.state_client.connect(refbox_ip, 1883)
#             for t in ('teamColor', 'pose', 'game_state', 'phase'):
#                 self.state_client.subscribe(f'{robot_ip}/{t}')
#             self.state_client.loop_start()
#             for _ in range(30):  # wait up to 3 s for team colour
#                 if self.team['color']:
#                     break
#                 time.sleep(0.1)
#             if self.team['color'] not in TEAM_PORT:
#                 raise SystemExit(f'refbox did not send a team colour for {robot_ip}; set team:=CYAN or MAGENTA')
#             self.report_topic = f'TEAM_{self.team["color"]}/report'
#             if self.dry_run:
#                 self.get_logger().info(f'DRY RUN: team {self.team["color"]}, reports are printed, not sent')
#             else:
#                 self.report_client = new_client()
#                 self.report_client.connect(refbox_ip, TEAM_PORT[self.team['color']])
#                 self.report_client.loop_start()
#                 self.get_logger().info(f'Refbox: team {self.team["color"]}, sending to {refbox_ip}:'
#                                        f'{TEAM_PORT[self.team["color"]]} topic {self.report_topic}')
#         elif not self.team['color']:
#             self.team['color'] = 'CYAN'

#         self.seen, self.last_seen_t, self.reported = {}, {}, set()
#         self.last_warn = self.last_print = 0.0

#         # ---------------- Camera ----------------
#         if not device:
#             cams = sorted(glob.glob('/dev/v4l/by-id/*-video-index0'))
#             if not cams:
#                 raise SystemExit('no USB webcam found (check lsusb / cable)')
#             device = os.path.realpath(cams[0])
#         self.get_logger().info(f'Using camera {device}, calibration {calib}, {self.fps:g} fps')
#         self.cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
#         if not self.cap.isOpened():
#             raise SystemExit(f'cannot open {device} (in use? check: sudo fuser -v {device})')
#         self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cal['image_width'])    # keep calibration resolution
#         self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cal['image_height'])
#         self.cap.set(cv2.CAP_PROP_FPS, self.fps)
#         self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
#         self.create_timer(1.0 / self.fps, self.tick)

#     # ---------------- same functions as standalone ----------------
#     def game_allows(self):
#         """Only report while the game runs. If the bridge never told us, allow."""
#         if self.game['state'] is None and self.game['phase'] is None:
#             return True
#         running = self.game['state'] is None or 'RUNNING' in self.game['state']
#         phase_ok = self.game['phase'] is None or \
#             any(ph in self.game['phase'] for ph in ('EXPLORATION', 'PRODUCTION'))
#         return running and phase_ok

#     def machine_on_field(self, cx, cz, nx, nz, side):
#         """Camera-frame marker + marker normal -> machine centre (x, y) and rotation (deg, refbox)."""
#         th = np.radians(270 - self.robot['yaw'])     # bridge sends yaw as (270 - map_yaw) % 360
#         fwd = np.array([np.cos(th), np.sin(th)])
#         right = np.array([np.sin(th), -np.cos(th)])
#         cam = np.array([self.robot['x'], self.robot['y']]) + fwd * self.cam_forward - right * self.cam_left
#         marker = cam + fwd * cz + right * cx
#         normal = right * nx + fwd * nz               # out of the machine, toward the camera
#         n = np.linalg.norm(normal)
#         if n < 1e-6:
#             return None
#         normal /= n
#         centre = marker - normal * self.center_offset
#         side_deg = np.degrees(np.arctan2(normal[1], normal[0]))
#         yaw = (270 - side_deg) % 360
#         if side == 'output':
#             yaw += 180
#         yaw = (yaw + self.yaw_offset) % 360
#         yaw = int(round(yaw / 45.0)) * 45 % 360
#         return float(centre[0]), float(centre[1]), yaw

#     def publish_report(self, payload, mid, info):
#         self.report_pub.publish(String(data=payload))                 # ROS topic
#         tag = 'DRY RUN, not sent' if self.dry_run or not self.report_client \
#             else f'sent to {self.report_topic}'
#         if self.report_client and not self.dry_run:
#             self.report_client.publish(self.report_topic, payload)    # RefBox (MQTT)
#         self.get_logger().info(f'-> REPORT {payload}  ({info}, marker {mid}, {tag})  '
#                                f'[{len(self.reported)}/{len(MACHINES)} markers]')

#     def process(self, found):
#         """Collect estimates; report each MARKER ID once (101, 102, 121, 122) when it is stable."""
#         now = time.time()
#         if self.no_pose:
#             for f in found:
#                 mid = f['id']
#                 if mid not in MACHINES:
#                     continue
#                 name = f'{self.team["color"][0]}-{MACHINES[mid][0]}'
#                 if mid in self.reported:    # each marker ID is reported once
#                     continue
#                 if not self.game_allows():
#                     if now - self.last_warn > 3:
#                         self.get_logger().info(f'(game not running: state={self.game["state"]} '
#                                                f'phase={self.game["phase"]})')
#                         self.last_warn = now
#                     return
#                 # bridge format (rcll-mqtt-bridge): exactly machine, x, y, yaw
#                 payload = json.dumps({'machine': name, 'x': 0, 'y': 0, 'yaw': 0})
#                 self.reported.add(mid)
#                 self.publish_report(payload, mid, f'no pose, {MACHINES[mid][1]}')
#             return
#         if now - self.robot['t'] > 2.0:
#             if now - self.last_warn > 3:
#                 self.get_logger().info('(no fresh /pose from the bridge - cannot place machines)')
#                 self.last_warn = now
#             return
#         for f in found:
#             mid = f['id']
#             if mid not in MACHINES:
#                 continue
#             name = f'{self.team["color"][0]}-{MACHINES[mid][0]}'
#             if mid in self.reported:        # each marker ID is reported once
#                 continue
#             est = self.machine_on_field(f['cx'], f['cz'], f['nx'], f['nz'], MACHINES[mid][1])
#             if est is None:
#                 continue
#             if now - self.last_seen_t.get(mid, 0) > 1.0:  # gap -> start counting again
#                 self.seen[mid] = []
#             self.last_seen_t[mid] = now
#             self.seen[mid].append(est)
#             hist = self.seen[mid][-self.confirm:]
#             if len(hist) < self.confirm:
#                 continue
#             xs = np.array([h[0] for h in hist])
#             ys = np.array([h[1] for h in hist])
#             yaws = {h[2] for h in hist}
#             mx, my = float(xs.mean()), float(ys.mean())
#             spread = float(np.max(np.hypot(xs - mx, ys - my)))
#             if spread > 0.15 or len(yaws) != 1:
#                 continue  # still moving / noisy - keep collecting
#             if not self.game_allows():
#                 if now - self.last_warn > 3:
#                     self.get_logger().info(f'(game not running: state={self.game["state"]} '
#                                            f'phase={self.game["phase"]})')
#                     self.last_warn = now
#                 continue
#             zone = zone_name(mx, my)
#             # bridge format (rcll-mqtt-bridge): exactly machine, x, y, yaw
#             payload = json.dumps({'machine': name, 'x': round(mx, 2), 'y': round(my, 2),
#                                   'yaw': yaws.pop()})
#             self.reported.add(mid)
#             self.publish_report(payload, mid, f'{zone}, {MACHINES[mid][1]}')

#     def detect(self, frame, draw):
#         """Detect markers. Returns (found list, text lines). Draws on frame only if draw=True."""
#         gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         corners, ids, _ = self.find_markers(gray)
#         if ids is None:
#             return [], []
#         if draw:
#             cv2.aruco.drawDetectedMarkers(frame, corners, ids)
#         found, lines = [], []
#         for c, mid in zip(corners, ids.ravel()):
#             mid = int(mid)
#             machine, side = MACHINES.get(mid, ('?', 'unknown'))
#             text = f'{mid} {machine} {side}'
#             line = f'id={mid} {machine}-{side}'
#             okp, rvec, tvec = cv2.solvePnP(self.obj, c.reshape(4, 2), self.K, self.D,
#                                            flags=cv2.SOLVEPNP_IPPE_SQUARE)
#             if okp:
#                 x, y, z = tvec.ravel()
#                 dist = float(np.linalg.norm(tvec))
#                 bearing = np.degrees(np.arctan2(x, z))
#                 R, _ = cv2.Rodrigues(rvec)
#                 yaw = np.degrees(np.arctan2(R[0, 2], -R[2, 2]))
#                 found.append({'id': mid, 'cx': float(x), 'cz': float(z),
#                               'nx': float(R[0, 2]), 'nz': float(R[2, 2]),
#                               'dist': dist, 'bearing': float(bearing), 'marker_yaw': float(yaw)})
#                 text += f' {dist:.2f}m {bearing:+.0f}deg'
#                 line += f': dist={dist:.3f}m bearing={bearing:+.1f}deg marker_yaw={yaw:+.1f}deg'
#                 if draw:
#                     cv2.drawFrameAxes(frame, self.K, self.D, rvec, tvec, self.size * 0.5)
#             lines.append(line)
#             if draw:
#                 pt = c.reshape(4, 2)[0].astype(int)
#                 cv2.putText(frame, text, (pt[0], max(pt[1] - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX,
#                             0.6, (0, 255, 0), 2)
#         return found, lines

#     def tick(self):
#         ok, frame = self.cap.read()
#         if not ok:
#             return
#         want_raw = self.img_pub.get_subscription_count() > 0
#         want_jpg = self.cimg_pub.get_subscription_count() > 0
#         found, lines = self.detect(frame, draw=want_raw or want_jpg)
#         now = time.time()
#         if lines and now - self.last_print > 1.0:
#             pose = (f'  [robot x={self.robot["x"]:.2f} y={self.robot["y"]:.2f} '
#                     f'yaw={self.robot["yaw"]:.0f}]') if self.refbox else ''
#             self.get_logger().info(' | '.join(lines) + pose)
#             self.last_print = now
#         if self.det_pub.get_subscription_count() > 0:
#             self.det_pub.publish(String(data=json.dumps({
#                 'stamp': round(now, 3),
#                 'markers': [{'id': f['id'],
#                              'machine': MACHINES.get(f['id'], ('?', 'unknown'))[0],
#                              'side': MACHINES.get(f['id'], ('?', 'unknown'))[1],
#                              'dist': round(f['dist'], 3), 'bearing': round(f['bearing'], 1),
#                              'marker_yaw': round(f['marker_yaw'], 1),
#                              'x': round(f['cx'], 3), 'z': round(f['cz'], 3)} for f in found]})))
#         if found:
#             self.process(found)
#         stamp = self.get_clock().now().to_msg()
#         if want_raw:
#             img = Image()
#             img.header.stamp = stamp
#             img.header.frame_id = 'camera'
#             img.height, img.width = frame.shape[:2]
#             img.encoding = 'bgr8'
#             img.step = img.width * 3
#             img.data = frame.tobytes()
#             self.img_pub.publish(img)
#         if want_jpg:
#             cimg = CompressedImage()
#             cimg.header.stamp = stamp
#             cimg.header.frame_id = 'camera'
#             cimg.format = 'jpeg'
#             cimg.data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])[1].tobytes()
#             self.cimg_pub.publish(cimg)

#     def close(self):
#         self.cap.release()
#         for c in (self.state_client, self.report_client):
#             if c:
#                 c.loop_stop()
#                 c.disconnect()


# def main(args=None):
#     rclpy.init(args=args)
#     node = ArucoNode()
#     try:
#         rclpy.spin(node)
#     except KeyboardInterrupt:
#         pass
#     node.close()
#     node.destroy_node()
#     if rclpy.ok():
#         rclpy.shutdown()


# if __name__ == '__main__':
#     main()

#!/usr/bin/env python3
# """Lightweight ArUco detector node (no MQTT, no RefBox, no pose maths).

# Publishes only:
#   /aruco/image_view/compressed  sensor_msgs/CompressedImage  camera view with markers drawn
#                                 (only encoded while something subscribes)
#   /aruco/detections             std_msgs/String, every frame with markers:
#                                 {"markers": [{"id": 101, "machine": "CS1", "side": "output",
#                                               "marker_yaw": -12.3}]}
#                                 marker_yaw: + / - degrees, 0 = facing the camera straight on

# Logs the markers it sees once every 3 seconds.

# Run:   ros2 run ired_aruco aruco_detect --ros-args -p size:=0.07
# """
# import glob
# import json
# import os
# import time

# import cv2
# import numpy as np
# import yaml

# import rclpy
# from rclpy.node import Node
# from sensor_msgs.msg import CompressedImage
# from std_msgs.msg import String

# # Marker ID -> (machine, side), from the challenge rules
# MACHINES = {
#     102: ('CS1', 'input'),
#     101: ('CS1', 'output'),
#     122: ('BS', 'input'),
#     121: ('BS', 'output'),
# }
# LOG_PERIOD = 3.0   # seconds between log lines


# class ArucoNode(Node):
#     def __init__(self):
#         super().__init__('aruco_detect')
#         P = self.declare_parameter
#         self.size = float(P('size', 0.07).value)
#         calib = P('calib', os.path.expanduser('~/.ros/camera_info/default_cam.yaml')).value
#         device = P('device', '').value
#         self.fps = float(P('fps', 10.0).value)
#         cv2.setNumThreads(int(P('threads', 1).value))

#         with open(calib) as f:
#             cal = yaml.safe_load(f)
#         self.K = np.array(cal['camera_matrix']['data'], dtype=np.float64).reshape(3, 3)
#         self.D = np.array(cal['distortion_coefficients']['data'], dtype=np.float64)

#         # ArUco detector: works with both old (<4.7) and new OpenCV APIs
#         aruco = cv2.aruco
#         dictionary = aruco.getPredefinedDictionary(aruco.DICT_ARUCO_ORIGINAL)
#         params = aruco.DetectorParameters() if hasattr(aruco, 'ArucoDetector') \
#             else aruco.DetectorParameters_create()
#         params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
#         if hasattr(aruco, 'ArucoDetector'):
#             det = aruco.ArucoDetector(dictionary, params)
#             self.find_markers = det.detectMarkers
#         else:
#             self.find_markers = lambda g: aruco.detectMarkers(g, dictionary, parameters=params)
#         s = self.size / 2
#         # marker corners in marker frame, same order as detectMarkers (TL, TR, BR, BL)
#         self.obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], dtype=np.float64)

#         # ---- publishers ----
#         self.cimg_pub = self.create_publisher(CompressedImage, '/aruco/image_view/compressed', 1)
#         self.det_pub = self.create_publisher(String, '/aruco/detections', 10)
#         self.last_log = 0.0

#         # ---- camera ----
#         if not device:
#             cams = sorted(glob.glob('/dev/v4l/by-id/*-video-index0'))
#             if not cams:
#                 raise SystemExit('no USB webcam found (check lsusb / cable)')
#             device = os.path.realpath(cams[0])
#         self.get_logger().info(f'Using camera {device}, marker size {self.size} m, {self.fps:g} fps')
#         self.cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
#         if not self.cap.isOpened():
#             raise SystemExit(f'cannot open {device} (in use? check: sudo fuser -v {device})')
#         self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cal['image_width'])    # keep calibration resolution
#         self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cal['image_height'])
#         self.cap.set(cv2.CAP_PROP_FPS, self.fps)
#         self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
#         self.create_timer(1.0 / self.fps, self.tick)

#     def detect(self, frame, draw):
#         """Returns a list of {id, machine, side, marker_yaw}. Draws on frame only if draw=True."""
#         gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
#         corners, ids, _ = self.find_markers(gray)
#         if ids is None:
#             return []
#         if draw:
#             cv2.aruco.drawDetectedMarkers(frame, corners, ids)
#         found = []
#         for c, mid in zip(corners, ids.ravel()):
#             mid = int(mid)
#             machine, side = MACHINES.get(mid, ('?', 'unknown'))
#             okp, rvec, tvec = cv2.solvePnP(self.obj, c.reshape(4, 2), self.K, self.D,
#                                            flags=cv2.SOLVEPNP_IPPE_SQUARE)
#             if not okp:
#                 continue
#             R, _ = cv2.Rodrigues(rvec)
#             yaw = float(np.degrees(np.arctan2(R[0, 2], -R[2, 2])))
#             found.append({'id': mid, 'machine': machine, 'side': side,
#                           'marker_yaw': round(yaw, 1)})
#             if draw:
#                 cv2.drawFrameAxes(frame, self.K, self.D, rvec, tvec, self.size * 0.5)
#                 pt = c.reshape(4, 2)[0].astype(int)
#                 cv2.putText(frame, f'{mid} {machine} {yaw:+.0f}deg',
#                             (pt[0], max(pt[1] - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX,
#                             0.6, (0, 255, 0), 2)
#         return found

#     def tick(self):
#         ok, frame = self.cap.read()
#         if not ok:
#             return
#         want_jpg = self.cimg_pub.get_subscription_count() > 0
#         found = self.detect(frame, draw=want_jpg)

#         if found:
#             self.det_pub.publish(String(data=json.dumps({'markers': found})))

#         now = time.time()
#         if now - self.last_log >= LOG_PERIOD:
#             if found:
#                 self.get_logger().info(' | '.join(
#                     f"{f['id']} {f['machine']} yaw={f['marker_yaw']:+.1f}" for f in found))
#             else:
#                 self.get_logger().info('no markers')
#             self.last_log = now

#         if want_jpg:
#             cimg = CompressedImage()
#             cimg.header.stamp = self.get_clock().now().to_msg()
#             cimg.header.frame_id = 'camera'
#             cimg.format = 'jpeg'
#             cimg.data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])[1].tobytes()
#             self.cimg_pub.publish(cimg)

#     def close(self):
#         self.cap.release()


# def main(args=None):
#     rclpy.init(args=args)
#     node = ArucoNode()
#     try:
#         rclpy.spin(node)
#     except KeyboardInterrupt:
#         pass
#     node.close()
#     node.destroy_node()
#     if rclpy.ok():
#         rclpy.shutdown()


# if __name__ == '__main__':
#     main()




#!/usr/bin/env python3
"""Lightweight ArUco detector node (no MQTT, no RefBox, no pose maths).

Publishes only:
  /aruco/image_view/compressed  sensor_msgs/CompressedImage  camera view with markers drawn
                                (only encoded while something subscribes)
  /aruco/detections             std_msgs/String, every frame with markers:
                                {"markers": [{"id": 101, "machine": "CS1", "side": "output",
                                              "marker_yaw": -12.3, "x": -0.05, "z": 0.62}]}
                                marker_yaw: + / - degrees, 0 = facing the camera straight on
                                x: metres right of the camera, z: metres in front of the camera

Logs the markers it sees once every 3 seconds.

Run:   ros2 run ired_aruco aruco_detect --ros-args -p size:=0.07
"""
import glob
import json
import os
import time

import cv2
import numpy as np
import yaml

import rclpy
from rclpy.node import Node
from sensor_msgs.msg import CompressedImage
from std_msgs.msg import String

# Marker ID -> (machine, side), from the challenge rules
MACHINES = {
    102: ('CS1', 'input'),
    101: ('CS1', 'output'),
    122: ('BS', 'input'),
    121: ('BS', 'output'),
}
LOG_PERIOD = 3.0   # seconds between log lines


class ArucoNode(Node):
    def __init__(self):
        super().__init__('aruco_detect')
        P = self.declare_parameter
        self.size = float(P('size', 0.07).value)
        calib = P('calib', os.path.expanduser('~/.ros/camera_info/default_cam.yaml')).value
        device = P('device', '').value
        self.fps = float(P('fps', 10.0).value)
        cv2.setNumThreads(int(P('threads', 1).value))

        with open(calib) as f:
            cal = yaml.safe_load(f)
        self.K = np.array(cal['camera_matrix']['data'], dtype=np.float64).reshape(3, 3)
        self.D = np.array(cal['distortion_coefficients']['data'], dtype=np.float64)

        # ArUco detector: works with both old (<4.7) and new OpenCV APIs
        aruco = cv2.aruco
        dictionary = aruco.getPredefinedDictionary(aruco.DICT_ARUCO_ORIGINAL)
        params = aruco.DetectorParameters() if hasattr(aruco, 'ArucoDetector') \
            else aruco.DetectorParameters_create()
        params.cornerRefinementMethod = aruco.CORNER_REFINE_SUBPIX
        if hasattr(aruco, 'ArucoDetector'):
            det = aruco.ArucoDetector(dictionary, params)
            self.find_markers = det.detectMarkers
        else:
            self.find_markers = lambda g: aruco.detectMarkers(g, dictionary, parameters=params)
        s = self.size / 2
        # marker corners in marker frame, same order as detectMarkers (TL, TR, BR, BL)
        self.obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], dtype=np.float64)

        # ---- publishers ----
        self.cimg_pub = self.create_publisher(CompressedImage, '/aruco/image_view/compressed', 1)
        self.det_pub = self.create_publisher(String, '/aruco/detections', 10)
        self.last_log = 0.0

        # ---- camera ----
        if not device:
            cams = sorted(glob.glob('/dev/v4l/by-id/*-video-index0'))
            if not cams:
                raise SystemExit('no USB webcam found (check lsusb / cable)')
            device = os.path.realpath(cams[0])
        self.get_logger().info(f'Using camera {device}, marker size {self.size} m, {self.fps:g} fps')
        self.cap = cv2.VideoCapture(device, cv2.CAP_V4L2)
        if not self.cap.isOpened():
            raise SystemExit(f'cannot open {device} (in use? check: sudo fuser -v {device})')
        self.cap.set(cv2.CAP_PROP_FRAME_WIDTH, cal['image_width'])    # keep calibration resolution
        self.cap.set(cv2.CAP_PROP_FRAME_HEIGHT, cal['image_height'])
        self.cap.set(cv2.CAP_PROP_FPS, self.fps)
        self.cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        self.create_timer(1.0 / self.fps, self.tick)

    def detect(self, frame, draw):
        """Returns a list of {id, machine, side, marker_yaw, x, z}. Draws on frame only if draw=True."""
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        corners, ids, _ = self.find_markers(gray)
        if ids is None:
            return []
        if draw:
            cv2.aruco.drawDetectedMarkers(frame, corners, ids)
        found = []
        for c, mid in zip(corners, ids.ravel()):
            mid = int(mid)
            machine, side = MACHINES.get(mid, ('?', 'unknown'))
            okp, rvec, tvec = cv2.solvePnP(self.obj, c.reshape(4, 2), self.K, self.D,
                                           flags=cv2.SOLVEPNP_IPPE_SQUARE)
            if not okp:
                continue
            R, _ = cv2.Rodrigues(rvec)
            yaw = float(np.degrees(np.arctan2(R[0, 2], -R[2, 2])))
            x, _, z = tvec.ravel()
            found.append({'id': mid, 'machine': machine, 'side': side,
                          'marker_yaw': round(yaw, 1),
                          'x': round(float(x), 3), 'z': round(float(z), 3)})
            if draw:
                cv2.drawFrameAxes(frame, self.K, self.D, rvec, tvec, self.size * 0.5)
                pt = c.reshape(4, 2)[0].astype(int)
                cv2.putText(frame, f'{mid} {machine} {yaw:+.0f}deg',
                            (pt[0], max(pt[1] - 10, 20)), cv2.FONT_HERSHEY_SIMPLEX,
                            0.6, (0, 255, 0), 2)
        return found

    def tick(self):
        ok, frame = self.cap.read()
        if not ok:
            return
        want_jpg = self.cimg_pub.get_subscription_count() > 0
        found = self.detect(frame, draw=want_jpg)

        if found:
            self.det_pub.publish(String(data=json.dumps({'markers': found})))

        now = time.time()
        if now - self.last_log >= LOG_PERIOD:
            if found:
                self.get_logger().info(' | '.join(
                    f"{f['id']} {f['machine']} yaw={f['marker_yaw']:+.1f} "
                    f"x={f['x']:+.2f} z={f['z']:.2f}m" for f in found))
            else:
                self.get_logger().info('no markers')
            self.last_log = now

        if want_jpg:
            cimg = CompressedImage()
            cimg.header.stamp = self.get_clock().now().to_msg()
            cimg.header.frame_id = 'camera'
            cimg.format = 'jpeg'
            cimg.data = cv2.imencode('.jpg', frame, [cv2.IMWRITE_JPEG_QUALITY, 60])[1].tobytes()
            self.cimg_pub.publish(cimg)

    def close(self):
        self.cap.release()


def main(args=None):
    rclpy.init(args=args)
    node = ArucoNode()
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    node.close()
    node.destroy_node()
    if rclpy.ok():
        rclpy.shutdown()


if __name__ == '__main__':
    main()