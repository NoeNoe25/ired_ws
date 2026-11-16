import os

from ament_index_python.packages import get_package_share_directory

from launch import LaunchDescription

from launch.actions import DeclareLaunchArgument, LogInfo, IncludeLaunchDescription

from launch.launch_description_sources import PythonLaunchDescriptionSource, AnyLaunchDescriptionSource

from launch.conditions import IfCondition

from launch.substitutions import LaunchConfiguration, Command

from launch_ros.actions import Node

from launch_ros.parameter_descriptions import ParameterValue


def generate_launch_description():

    param_dir = LaunchConfiguration(
        'param_dir',
        default=os.path.join(
            get_package_share_directory('ired_bringup'),
            'param',
            'ired.yaml'
        )
    )

    laser_param_dir = LaunchConfiguration(
        'laser_param_dir',
        default=os.path.join(
            get_package_share_directory('ired_bringup'),
            'param',
            'laser_config.yaml'
        )
    )

    urdf_file = os.path.join(
        get_package_share_directory('ired_bringup'),
        'urdf',
        'ired.urdf.xacro'
    )

    # Convert Xacro output explicitly to a string
    robot_description = ParameterValue(
        Command(['xacro ', urdf_file]),
        value_type=str
    )

    rplidar_launch = LaunchConfiguration(
        'rplidar_launch',
        default=os.path.join(
            get_package_share_directory('rplidar_ros'),
            'launch'
        )
    )

    use_navigation = LaunchConfiguration('use_navigation')
    use_aruco = LaunchConfiguration('use_aruco')

    return LaunchDescription([

        LogInfo(
            msg=['Starting iRED Bringup...']
        ),

        DeclareLaunchArgument(
            'param_dir',
            default_value=param_dir,
            description='Specifying parameter direction'
        ),

        DeclareLaunchArgument(
            'use_navigation',
            default_value='true',
            description='Start map server, AMCL localization and Nav2 (ired_navigation)'
        ),

        DeclareLaunchArgument(
            'use_aruco',
            default_value='true',
            description='Start camera, ArUco station detection and refbox station reports (ired_aruco)'
        ),

        Node(
            package='robot_state_publisher',
            executable='robot_state_publisher',
            name='robot_state_publisher',
            output='screen',
            parameters=[
                {
                    'robot_description': robot_description,
                    'publish_frequency': 10.0
                }
            ]
        ),

        Node(
            package='ired_bringup',
            executable='forward_kinematics',
            parameters=[param_dir],
            output='screen'
        ),

        Node(
            package='ired_bringup',
            executable='inverse_kinematics',
            parameters=[param_dir],
            output='screen'
        ),

        Node(
            package='ired_bringup',
            executable='imu_node',
            parameters=[param_dir],
            output='screen'
        ),

        Node(
            package='ired_bringup',
            executable='odom_node',
            parameters=[param_dir],
            output='screen'
        ),

        Node(
            package='ired_bringup',
            executable='modbus_serial',
            parameters=[param_dir],
            output='screen'
        ),

        IncludeLaunchDescription(
            PythonLaunchDescriptionSource(
                [rplidar_launch, '/rplidar_a1_launch.py']
            ),
            launch_arguments={
                'serial_port': '/dev/ttyLiDAR',
                'serial_baudrate': '115200',
                'frame_id': 'base_scan'
            }.items()
        ),

        Node(
            package='laser_filters',
            executable='scan_to_scan_filter_chain',
            parameters=[param_dir],
            output='screen'
        ),

        # Retries every 5 s while the refbox MQTT bridge is not reachable
   #     Node(
  #          package='ired_refbox',
 #           executable='mqtt_refbox',
 #           output='screen',
        #     respawn=True,
        #     respawn_delay=5.0
#        ),

        # Map server + AMCL (initial pose in ired_navigation/param/navigation.yaml) + Nav2
        # IncludeLaunchDescription(
        #     AnyLaunchDescriptionSource(
        #         os.path.join(get_package_share_directory('ired_navigation'), 'launch', 'navigation.launch.xml')
        #     ),
        #     condition=IfCondition(use_navigation)
        # ),

        # Camera + ArUco detector; reports only once AMCL localization and TF are available
        # IncludeLaunchDescription(
        #     PythonLaunchDescriptionSource(
        #         os.path.join(get_package_share_directory('ired_aruco'), 'launch', 'aruco.launch.py')
        #     ),
        #     launch_arguments={'report_to_refbox': 'true'}.items(),
        #     condition=IfCondition(use_aruco)
        # )

    ])
