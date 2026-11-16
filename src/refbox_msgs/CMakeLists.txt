cmake_minimum_required(VERSION 3.8)
project(refbox_msgs)

if(CMAKE_COMPILER_IS_GNUCXX OR CMAKE_CXX_COMPILER_ID MATCHES "Clang")
  add_compile_options(-Wall -Wextra -Wpedantic)
endif()

find_package(ament_cmake REQUIRED)
find_package(std_msgs REQUIRED)
find_package(rosidl_default_generators REQUIRED)

rosidl_generate_interfaces(${PROJECT_NAME}
  "msg/GameInfo.msg"
  "msg/MachineInfoData.msg"
  "msg/NavigationPosition.msg"
  "msg/NavigationRoutes.msg"
  "msg/GamePlay.msg"
  "msg/MachineInfo.msg"
  "msg/NavigationRoutesData.msg"
  "msg/NavigationRoutesPoint.msg"
  "srv/MachineReport.srv"
  DEPENDENCIES std_msgs
)

if(BUILD_TESTING)
  find_package(ament_lint_auto REQUIRED)
  set(ament_cmake_copyright_FOUND TRUE)
  set(ament_cmake_cpplint_FOUND TRUE)
  ament_lint_auto_find_test_dependencies()
endif()

ament_package()
