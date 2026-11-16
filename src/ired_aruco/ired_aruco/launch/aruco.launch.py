"""Start ArUco detection + pose/zone (sends robot pose) + report (sends machines).

  ros2 launch ired_aruco aruco.launch.py team:=CYAN
  ros2 launch ired_aruco aruco.launch.py team:=CYAN dry_run:=true     # test, reports not sent
"""
from launch import LaunchDescription
from launch.actions import DeclareLaunchArgument
from launch.substitutions import LaunchConfiguration
from launch_ros.actions import Node
from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():
    args = {
        'team': 'CYAN',
        'size': '0.07',             # marker size (m)
        'fps': '10.0',
        'broker': '172.16.0.245',   # bridge VM
        'robot_ip': '172.16.0.24',
        'confirm': '5',             # sightings in a row before reporting
        'dry_run': 'false',         # true = print reports, don't send
        'refbox_yaw': 'true',       # pose yaw as (270 - map_yaw) % 360
    }
    declares = [DeclareLaunchArgument(k, default_value=v) for k, v in args.items()]
    L = LaunchConfiguration

    detect = Node(
        package='ired_aruco', executable='aruco_detect', name='aruco_detect', output='screen',
        parameters=[{
            'size': ParameterValue(L('size'), value_type=float),
            'fps': ParameterValue(L('fps'), value_type=float),
        }],
    )

    pose_zone = Node(
        package='ired_aruco', executable='pose_zone', name='pose_zone_node', output='screen',
        parameters=[{
            'broker': ParameterValue(L('broker'), value_type=str),
            'robot_ip': ParameterValue(L('robot_ip'), value_type=str),
            'refbox_yaw': ParameterValue(L('refbox_yaw'), value_type=bool),
        }],
    )

    report = Node(
        package='ired_aruco', executable='aruco_report', name='aruco_report_node', output='screen',
        parameters=[{
            'team': ParameterValue(L('team'), value_type=str),
            'broker': ParameterValue(L('broker'), value_type=str),
            'robot_ip': ParameterValue(L('robot_ip'), value_type=str),
            'confirm': ParameterValue(L('confirm'), value_type=int),
            'dry_run': ParameterValue(L('dry_run'), value_type=bool),
        }],
    )

    return LaunchDescription(declares + [detect, pose_zone, report])