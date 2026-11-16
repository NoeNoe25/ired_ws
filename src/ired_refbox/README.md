# ired_refbox

`ired_refbox` is a ROS2 package designed to interface with the iRED Refbox system via MQTT.  
It handles game information, navigation routes, machine info, and robot pose, and provides a ROS2 service to publish machine reports via MQTT.

---

## Repositories

1. [refbox_msgs](http://gitlab.raikmitl.com/ired/refbox_msgs.git) – ROS2 message and service definitions.  
2. [ired_refbox](http://gitlab.raikmitl.com/ired/ired_refbox.git) – ROS2 nodes implementing the Refbox interface.

---

## Package Requirements

Install the required packages:

```
sudo apt update
sudo apt install python3-paho-mqtt
sudo apt install ros-jazzy-tf-transformations
```

## Environment Setup
Add the following environment variables to your ROS2 workspace environment (`ros_environment.bash`):
```
$ nano ~/ros_environment.bash
# Refbox MQTT Bridge
export REFBOX_BRIDGE_ADDRESS=172.16.0.11 # Refbox bridge address
export ROBOT_IP=172.16.0.200 # your robot ip address
```
Source your ROS2 workspace and environment:
```
source ~/ros_environment.bash
```
## Build the Workspace
Clone the repositories into your ROS2 workspace src folder:
```
cd ~/ired_ws/src
git clone -b jazzy http://gitlab.raikmitl.com/ired/refbox_msgs.git
git clone -b jazzy http://gitlab.raikmitl.com/ired/ired_refbox.git
```
Then build the workspace:
```
cd ~/ired_ws
colcon build --symlink-install
source install/setup.bash
```
## Running the Refbox Node
Run the mqtt_refbox node:
```
ros2 run ired_refbox mqtt_refbox
```
## ROS2 Topics
The `mqtt_refbox` node publishes the following topics:

| Topic | Message Type | Description |
| :------ | :---------: | :---------- |
| `/refbox/navigation_routes` | `ired_refbox/NavigationRoutesData` | Navigation routes for the robot. |
| `/refbox/machine_info` | `ired_refbox/MachineInfoData` | Latest machine information in the environment. |
| `/refbox/game_info` | `ired_refbox/GameInfo` | Current game state and phase. |
| `/refbox/game_play` | `ired_refbox/GamePlay` | Game play status (`True` if running). |


The node subscribes to:

| Topic | Message Type | Description |
| :------ | :---------: | :---------- |
| `/amcl_pose` | `geometry_msgs/PoseWithCovarianceStamped` | Robot pose used to publish MQTT position updates. |

# ROS2 Services
The mqtt_refbox node provides the following service:
| Service | Service Type | Description |
| :--- | :---: | :--- |
| `/refbox/machine_report` | `refbox_msgs/srv/MachineReport` | Publish a machine report to the MQTT bridge. Request contains machine, x, y, yaw. Response contains status (True if successfully published).|