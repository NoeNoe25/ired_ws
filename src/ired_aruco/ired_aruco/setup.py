from glob import glob
import os

from setuptools import setup

package_name = 'ired_aruco'

setup(
    name=package_name,
    version='0.1.0',
    packages=[package_name],
    data_files=[
        ('share/ament_index/resource_index/packages', ['resource/' + package_name]),
        ('share/' + package_name, ['package.xml']),
        (os.path.join('share', package_name, 'launch'), glob('launch/*.launch.py')),
    ],
    install_requires=['setuptools'],
    zip_safe=True,
    maintainer='ired',
    maintainer_email='ired@todo.todo',
    description='ArUco machine-marker detector for the RefBox',
    license='MIT',
    entry_points={
        'console_scripts': [
        'aruco_detect = ired_aruco.aruco_detect:main',
        'pose_zone = ired_aruco.aruco_zone_node:main',
        'aruco_report = ired_aruco.aruco_report_node:main',
    ],
    },
)
