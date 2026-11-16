# #!/usr/bin/env python3
# """Navigation Challenge: drive through every zone of the RefBox route with Nav2.

# - Reads the route from /refbox/navigation_routes and the game state from /refbox/game_play.
# - Drives through the red zone C_Z32 first (rule), then every zone of the route in order.
# - Goes to the zone CENTRE (RefBox position = zone corner, so centre = corner - 0.5).
# - Waits WAIT_IN_ZONE s in each zone (RefBox needs >= 5 s).
# - Uses the RefBox 'remaining' list: zones the RefBox already confirmed are skipped.
# - Failed goal -> retry, then skip and continue. After one pass, zones still in 'remaining'
#   get a second try.
# - Game paused -> cancel the goal and stop; when the game resumes, continue from the
#   remaining zones.
# - Set the start pose with 2D Pose Estimate in RViz BEFORE starting this node.
# """
# import math
# import threading
# import time

# import rclpy
# from rclpy.node import Node
# from geometry_msgs.msg import PoseStamped
# from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
# from refbox_msgs.msg import GamePlay, NavigationRoutesData

# RED_ZONE = 'C_Z32'          # Magenta: 'M_Z32'
# RED_ZONE_XY = (2.5, 1.5)    # Magenta: (-2.5, 1.5)
# WAIT_IN_ZONE = 6.0          # seconds inside each zone (RefBox needs >= 5 s)
# RETRIES = 1                 # extra tries per zone before skipping it
# MAX_PASSES = 2              # passes over the route (2nd pass = zones the RefBox did not confirm)


# class NavigationChallenge(Node):
#     def __init__(self):
#         super().__init__('navigation_challenge_node')

#         self.game_play_msg = GamePlay()
#         self.navigation_routes_msg = NavigationRoutesData()
#         self.lock = threading.Lock()
#         self.route_thread = None
#         self.route_running = False

#         # progress (kept across pauses)
#         self.red_done = False
#         self.done = set()           # zones finished in this pass (visited or skipped)
#         self.fail_count = {}
#         self.passes = 1
#         self.last_xy = None
#         self.t_start = None

#         self.create_subscription(GamePlay, "/refbox/game_play", self.commandGamePlayCallback, 10)
#         self.create_subscription(NavigationRoutesData, "/refbox/navigation_routes",
#                                  self.commandNavigationRouteCallback, 10)
#         self.timer = self.create_timer(0.2, self.update_callback)

#         self.navigator = BasicNavigator()
#         # 'robot_localization' skips BasicNavigator's initial-pose step, which would publish
#         # (0, 0) to /initialpose and reset AMCL. It still waits for bt_navigator to be active.
#         self.navigator.waitUntilNav2Active(localizer='robot_localization')

#         self.get_logger().info("Navigation Challenge ready: waiting for route + game RUNNING "
#                                "(/refbox/navigation_routes, /refbox/game_play)")

#     # ---------------- callbacks ----------------
#     def commandGamePlayCallback(self, msg):
#         with self.lock:
#             self.game_play_msg = msg

#     def commandNavigationRouteCallback(self, msg):
#         with self.lock:
#             self.navigation_routes_msg = msg

#     def game_on(self):
#         with self.lock:
#             return bool(self.game_play_msg.status)

#     def update_callback(self):
#         """Start (or restart after a pause) the route thread."""
#         if self.route_running:
#             return
#         with self.lock:
#             has_routes = len(self.navigation_routes_msg.routes) != 0
#             game_on = bool(self.game_play_msg.status)
#         if game_on and has_routes:
#             self.route_running = True
#             if self.t_start is None:
#                 self.t_start = time.time()
#             self.get_logger().info("Game RUNNING -> starting / resuming route")
#             self.route_thread = threading.Thread(target=self.run_route, daemon=True)
#             self.route_thread.start()

#     # ---------------- helpers ----------------
#     def make_pose(self, x, y, yaw, frame="map"):
#         import tf_transformations
#         pose = PoseStamped()
#         pose.header.frame_id = frame
#         pose.header.stamp = rclpy.clock.Clock().now().to_msg()
#         pose.pose.position.x = x
#         pose.pose.position.y = y
#         pose.pose.position.z = 0.0
#         q = tf_transformations.quaternion_from_euler(0, 0, yaw)
#         pose.pose.orientation.x = q[0]
#         pose.pose.orientation.y = q[1]
#         pose.pose.orientation.z = q[2]
#         pose.pose.orientation.w = q[3]
#         return pose

#     @staticmethod
#     def zone_centre(p):
#         """RefBox position = zone corner (e.g. C_Z45 -> 4,5). Centre is 0.5 m inside.
#         Magenta zones (M_) are mirrored to negative x."""
#         x, y = p.position.x, p.position.y
#         # mqtt_refbox always sends a positive x (digit from the zone name), so use the prefix
#         cx = -(x - 0.5) if p.zone.startswith('M_') else x - 0.5
#         return cx, y - 0.5

#     def moveToPoint(self, x, y, yaw):
#         """Returns 'ok', 'failed' or 'paused'."""
#         self.navigator.clearAllCostmaps()
#         if not self.navigator.goToPose(self.make_pose(x, y, yaw)):
#             self.get_logger().error('Goal rejected by Nav2')
#             return 'failed'
#         while rclpy.ok():
#             if not self.game_on():
#                 self.get_logger().warn("Game paused -> cancel goal")
#                 self.navigator.cancelTask()
#                 return 'paused'
#             if self.navigator.isTaskComplete():
#                 break
#             time.sleep(0.1)
#         result = self.navigator.getResult()
#         if result == TaskResult.SUCCEEDED:
#             return 'ok'
#         if result == TaskResult.CANCELED and not self.game_on():
#             return 'paused'
#         return 'failed'

#     def wait_in_zone(self):
#         """Stay in the zone. Returns False if the game was paused meanwhile."""
#         end = time.time() + WAIT_IN_ZONE
#         while time.time() < end:
#             if not self.game_on():
#                 return False
#             time.sleep(0.1)
#         return True

#     def heading_to(self, x, y):
#         if self.last_xy is None:
#             return 0.0
#         return math.atan2(y - self.last_xy[1], x - self.last_xy[0])

#     def go_zone(self, name, x, y):
#         """Drive to a zone centre and wait there. Returns 'ok', 'failed' or 'paused'."""
#         self.get_logger().info(f"-> {name} centre ({x:.1f}, {y:.1f})")
#         res = self.moveToPoint(x, y, self.heading_to(x, y))
#         if res != 'ok':
#             return res
#         self.last_xy = (x, y)
#         self.get_logger().info(f"   {name} reached, waiting {WAIT_IN_ZONE:.0f} s")
#         return 'ok' if self.wait_in_zone() else 'paused'

#     def next_target(self):
#         """First zone of the route that is still remaining at the RefBox and not done locally."""
#         with self.lock:
#             routes = self.navigation_routes_msg.routes
#             if not routes:
#                 return None
#             route = list(routes[0].route)
#             remaining = {p.zone for p in routes[0].remaining}
#         if not remaining:
#             return 'FINISHED'
#         for p in route:
#             if p.zone in self.done:
#                 continue
#             if p.zone not in remaining:          # RefBox already confirmed it
#                 self.done.add(p.zone)
#                 continue
#             return p
#         # pass finished, but some zones still not confirmed -> another pass
#         if self.passes < MAX_PASSES:
#             self.passes += 1
#             self.get_logger().warn(f"Pass {self.passes}: retrying unconfirmed zones {sorted(remaining)}")
#             self.done = {z for z in self.done if z not in remaining}
#             self.fail_count = {}
#             return self.next_target()
#         return 'FINISHED'

#     # ---------------- main route ----------------
#     def run_route(self):
#         try:
#             # 1) red zone first (rule)
#             if not self.red_done:
#                 res = self.go_zone(RED_ZONE + ' (red zone)', *RED_ZONE_XY)
#                 if res == 'paused':
#                     return
#                 if res == 'failed':
#                     self.get_logger().error("Red zone not reached - continuing anyway")
#                 self.red_done = True

#             # 2) all route zones
#             while rclpy.ok():
#                 p = self.next_target()
#                 if p is None:
#                     self.get_logger().warn("No route data")
#                     return
#                 if p == 'FINISHED':
#                     mins = (time.time() - self.t_start) / 60 if self.t_start else 0
#                     self.get_logger().info(f"ROUTE FINISHED in {mins:.1f} min")
#                     return
#                 x, y = self.zone_centre(p)
#                 res = self.go_zone(p.zone, x, y)
#                 if res == 'paused':
#                     return                              # resume later from remaining zones
#                 if res == 'ok':
#                     self.done.add(p.zone)
#                     continue
#                 n = self.fail_count.get(p.zone, 0) + 1
#                 self.fail_count[p.zone] = n
#                 if n > RETRIES:
#                     self.get_logger().error(f"   {p.zone} failed {n}x -> skipping")
#                     self.done.add(p.zone)
#                 else:
#                     self.get_logger().warn(f"   {p.zone} failed -> retry")
#         finally:
#             self.route_running = False


# def main(args=None):
#     rclpy.init(args=args)
#     challenge_node = NavigationChallenge()
#     navigator_node = challenge_node.navigator

#     from rclpy.executors import MultiThreadedExecutor
#     executor = MultiThreadedExecutor(num_threads=4)
#     executor.add_node(challenge_node)   # navigator spins itself inside BasicNavigator calls
#     try:
#         executor.spin()
#     except KeyboardInterrupt:
#         pass
#     finally:
#         executor.shutdown()
#         challenge_node.destroy_node()
#         navigator_node.destroy_node()
#         rclpy.shutdown()


# if __name__ == '__main__':
#     main()

#!/usr/bin/env python3
"""Navigation Challenge: drive through every zone of the RefBox route with Nav2.

- Reads the route from /refbox/navigation_routes and the game state from /refbox/game_play.
- Drives through the red zone C_Z32 first (rule), then every zone of the route in order.
- Goes to the zone CENTRE (RefBox position = zone corner, so centre = corner - 0.5).
- If the centre is blocked (obstacle), tries fallback points inside the zone
  (centre +/- ZONE_OFFSET in x and y).
- Waits WAIT_IN_ZONE s in each zone (RefBox needs >= 5 s).
- Uses the RefBox 'remaining' list: zones the RefBox already confirmed are skipped.
- Failed goal -> retry, then skip and continue. After one pass, zones still in 'remaining'
  get a second try.
- Game paused -> cancel the goal and stop; when the game resumes, continue from the
  remaining zones.
- Set the start pose with 2D Pose Estimate in RViz BEFORE starting this node.

Change the offset without editing code:
  ros2 run <pkg> navigation_challenge --ros-args -p zone_offset:=0.15
"""
import math
import threading
import time

import rclpy
from rclpy.node import Node
from geometry_msgs.msg import PoseStamped
from nav2_simple_commander.robot_navigator import BasicNavigator, TaskResult
from refbox_msgs.msg import GamePlay, NavigationRoutesData

RED_ZONE = 'C_Z32'          # Magenta: 'M_Z32'
RED_ZONE_XY = (2.5, 1.5)    # Magenta: (-2.5, 1.5)
WAIT_IN_ZONE = 5.0          # seconds inside each zone (RefBox needs >= 5 s)
RETRIES = 1                 # extra tries per zone before skipping it
MAX_PASSES = 2              # passes over the route (2nd pass = zones the RefBox did not confirm)

ZONE_OFFSET = 0.35           # default fallback distance from zone centre [m]
                            # keep <= 0.5 - robot_radius so the robot stays inside the zone
USE_DIAGONALS = False       # True -> also try the 4 diagonal points


class NavigationChallenge(Node):
    def __init__(self):
        super().__init__('navigation_challenge_node')

        # zone offset as ROS parameter (default = ZONE_OFFSET)
        self.declare_parameter('zone_offset', ZONE_OFFSET)
        self.declare_parameter('use_diagonals', USE_DIAGONALS)
        off = float(self.get_parameter('zone_offset').value)
        diag = bool(self.get_parameter('use_diagonals').value)
        self.zone_offsets = self.build_offsets(off, diag)
        self.get_logger().info(f"Zone offset = {off:.2f} m, {len(self.zone_offsets)} points per zone")

        self.game_play_msg = GamePlay()
        self.navigation_routes_msg = NavigationRoutesData()
        self.lock = threading.Lock()
        self.route_thread = None
        self.route_running = False

        # progress (kept across pauses)
        self.red_done = False
        self.done = set()           # zones finished in this pass (visited or skipped)
        self.fail_count = {}
        self.passes = 1
        self.last_xy = None
        self.t_start = None

        self.create_subscription(GamePlay, "/refbox/game_play", self.commandGamePlayCallback, 10)
        self.create_subscription(NavigationRoutesData, "/refbox/navigation_routes",
                                 self.commandNavigationRouteCallback, 10)
        self.timer = self.create_timer(0.2, self.update_callback)

        self.navigator = BasicNavigator()
        # 'robot_localization' skips BasicNavigator's initial-pose step, which would publish
        # (0, 0) to /initialpose and reset AMCL. It still waits for bt_navigator to be active.
        self.navigator.waitUntilNav2Active(localizer='robot_localization')

        self.get_logger().info("Navigation Challenge ready: waiting for route + game RUNNING "
                               "(/refbox/navigation_routes, /refbox/game_play)")

    @staticmethod
    def build_offsets(off, diagonals):
        """Centre first, then +/-off in x and y (optionally diagonals)."""
        pts = [(0.0, 0.0), (off, 0.0), (-off, 0.0), (0.0, off), (0.0, -off)]
        if diagonals:
            pts += [(off, off), (-off, off), (off, -off), (-off, -off)]
        return pts

    # ---------------- callbacks ----------------
    def commandGamePlayCallback(self, msg):
        with self.lock:
            self.game_play_msg = msg

    def commandNavigationRouteCallback(self, msg):
        with self.lock:
            self.navigation_routes_msg = msg

    def game_on(self):
        with self.lock:
            return bool(self.game_play_msg.status)

    def update_callback(self):
        """Start (or restart after a pause) the route thread."""
        if self.route_running:
            return
        with self.lock:
            has_routes = len(self.navigation_routes_msg.routes) != 0
            game_on = bool(self.game_play_msg.status)
        if game_on and has_routes:
            self.route_running = True
            if self.t_start is None:
                self.t_start = time.time()
            self.get_logger().info("Game RUNNING -> starting / resuming route")
            self.route_thread = threading.Thread(target=self.run_route, daemon=True)
            self.route_thread.start()

    # ---------------- helpers ----------------
    def make_pose(self, x, y, yaw, frame="map"):
        import tf_transformations
        pose = PoseStamped()
        pose.header.frame_id = frame
        pose.header.stamp = rclpy.clock.Clock().now().to_msg()
        pose.pose.position.x = x
        pose.pose.position.y = y
        pose.pose.position.z = 0.0
        q = tf_transformations.quaternion_from_euler(0, 0, yaw)
        pose.pose.orientation.x = q[0]
        pose.pose.orientation.y = q[1]
        pose.pose.orientation.z = q[2]
        pose.pose.orientation.w = q[3]
        return pose

    @staticmethod
    def zone_centre(p):
        """RefBox position = zone corner (e.g. C_Z45 -> 4,5). Centre is 0.5 m inside.
        Magenta zones (M_) are mirrored to negative x."""
        x, y = p.position.x, p.position.y
        # mqtt_refbox always sends a positive x (digit from the zone name), so use the prefix
        cx = -(x - 0.5) if p.zone.startswith('M_') else x - 0.5
        return cx, y - 0.5

    def moveToPoint(self, x, y, yaw):
        """Returns 'ok', 'failed' or 'paused'."""
        if not self.navigator.goToPose(self.make_pose(x, y, yaw)):
            self.get_logger().error('Goal rejected by Nav2')
            return 'failed'
        while rclpy.ok():
            if not self.game_on():
                self.get_logger().warn("Game paused -> cancel goal")
                self.navigator.cancelTask()
                return 'paused'
            if self.navigator.isTaskComplete():
                break
            time.sleep(0.1)
        result = self.navigator.getResult()
        if result == TaskResult.SUCCEEDED:
            return 'ok'
        if result == TaskResult.CANCELED and not self.game_on():
            return 'paused'
        self.navigator.clearAllCostmaps()   # clear only after a failure, before the next try
        return 'failed'

    def wait_in_zone(self):
        """Stay in the zone. Returns False if the game was paused meanwhile."""
        end = time.time() + WAIT_IN_ZONE
        while time.time() < end:
            if not self.game_on():
                return False
            time.sleep(0.1)
        return True

    def heading_to(self, x, y):
        if self.last_xy is None:
            return 0.0
        return math.atan2(y - self.last_xy[1], x - self.last_xy[0])

    def go_zone(self, name, x, y):
        """Drive into a zone (centre first, then offset points) and wait there.
        Returns 'ok', 'failed' or 'paused'."""
        for i, (dx, dy) in enumerate(self.zone_offsets):
            tx, ty = x + dx, y + dy
            label = "centre" if i == 0 else f"offset ({dx:+.2f}, {dy:+.2f})"
            self.get_logger().info(f"-> {name} {label} ({tx:.2f}, {ty:.2f})")
            res = self.moveToPoint(tx, ty, self.heading_to(tx, ty))
            if res == 'paused':
                return 'paused'
            if res == 'ok':
                self.last_xy = (tx, ty)
                self.get_logger().info(f"   {name} reached, waiting {WAIT_IN_ZONE:.0f} s")
                return 'ok' if self.wait_in_zone() else 'paused'
            self.get_logger().warn(f"   {name} {label} failed, trying next point")
        return 'failed'

    def next_target(self):
        """First zone of the route that is still remaining at the RefBox and not done locally."""
        with self.lock:
            routes = self.navigation_routes_msg.routes
            if not routes:
                return None
            route = list(routes[0].route)
            remaining = {p.zone for p in routes[0].remaining}
        if not remaining:
            return 'FINISHED'
        for p in route:
            if p.zone in self.done:
                continue
            if p.zone not in remaining:          # RefBox already confirmed it
                self.done.add(p.zone)
                continue
            return p
        # pass finished, but some zones still not confirmed -> another pass
        if self.passes < MAX_PASSES:
            self.passes += 1
            self.get_logger().warn(f"Pass {self.passes}: retrying unconfirmed zones {sorted(remaining)}")
            self.done = {z for z in self.done if z not in remaining}
            self.fail_count = {}
            return self.next_target()
        return 'FINISHED'

    # ---------------- main route ----------------
    def run_route(self):
        try:
            # 1) red zone first (rule)
            if not self.red_done:
                res = self.go_zone(RED_ZONE + ' (red zone)', *RED_ZONE_XY)
                if res == 'paused':
                    return
                if res == 'failed':
                    self.get_logger().error("Red zone not reached - continuing anyway")
                self.red_done = True

            # 2) all route zones
            while rclpy.ok():
                p = self.next_target()
                if p is None:
                    self.get_logger().warn("No route data")
                    return
                if p == 'FINISHED':
                    mins = (time.time() - self.t_start) / 60 if self.t_start else 0
                    self.get_logger().info(f"ROUTE FINISHED in {mins:.1f} min")
                    return
                x, y = self.zone_centre(p)
                res = self.go_zone(p.zone, x, y)
                if res == 'paused':
                    return                              # resume later from remaining zones
                if res == 'ok':
                    self.done.add(p.zone)
                    continue
                n = self.fail_count.get(p.zone, 0) + 1
                self.fail_count[p.zone] = n
                if n > RETRIES:
                    self.get_logger().error(f"   {p.zone} failed {n}x -> skipping")
                    self.done.add(p.zone)
                else:
                    self.get_logger().warn(f"   {p.zone} failed -> retry")
        finally:
            self.route_running = False


def main(args=None):
    rclpy.init(args=args)
    challenge_node = NavigationChallenge()
    navigator_node = challenge_node.navigator

    from rclpy.executors import MultiThreadedExecutor
    executor = MultiThreadedExecutor(num_threads=4)
    executor.add_node(challenge_node)   # navigator spins itself inside BasicNavigator calls
    try:
        executor.spin()
    except KeyboardInterrupt:
        pass
    finally:
        executor.shutdown()
        challenge_node.destroy_node()
        navigator_node.destroy_node()
        rclpy.shutdown()


if __name__ == '__main__':
    main()