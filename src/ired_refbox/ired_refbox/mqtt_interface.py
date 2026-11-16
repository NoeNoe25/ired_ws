import os
import paho.mqtt.client as mqtt
import json

class RobotMQTTClient:
    def __init__(self):
        # Setup MQTT Parameters
        self.mqtt_broker_address_ = os.environ.get('REFBOX_BRIDGE_ADDRESS')
        self.robot_ip_ = os.environ.get('ROBOT_IP')
        self.client = mqtt.Client()

        # Store latest game state, phase, team color, and navigation routes
        self.latest_game_state_ = None
        self.latest_phase_ = None
        self.latest_team_color_ = None
        self.latest_navigation_routes_ = None
        self.latest_machine_info_ = None

        # Setup MQTT event handlers
        self.client.on_connect = self.on_connect
        self.client.on_message = self.on_message

    def on_message(self, client, userdata, message):
        try:
            payload_str = message.payload.decode().strip()
            if not payload_str:
                return
            
            if message.topic == f"{self.robot_ip_}/private/navigation_routes":
                try:
                    self.latest_navigation_routes_ = json.loads(payload_str)
                except json.JSONDecodeError:
                    return None
            
            if message.topic == f"{self.robot_ip_}/private/machine_info":
                try:
                    self.latest_machine_info_ = json.loads(payload_str)
                except json.JSONDecodeError:
                    return None
            
            if message.topic == f"{self.robot_ip_}/game_state":
                self.latest_game_state_ = payload_str

            if message.topic == f"{self.robot_ip_}/phase":
                self.latest_phase_ = payload_str

            if message.topic == f"{self.robot_ip_}/teamColor":
                self.latest_team_color_ = payload_str

        except Exception as e:
            return

    def on_connect(self, client, userdata, flags, rc):
        if rc == 0:
            topics = [
                f"{self.robot_ip_}/game_state",
                f"{self.robot_ip_}/phase",
                f"{self.robot_ip_}/teamColor",
                f"{self.robot_ip_}/private/navigation_routes",
                f"{self.robot_ip_}/private/machine_info",
                "private/#"
            ]
            for topic in topics:
                client.subscribe(topic)
        else:
            return
    
    def robot_position(self, x, y, yaw):
        return {
            "x": x,
            "y": y,
            "yaw": yaw
        }

    def robot_position_publish(self, x, y, yaw):
        try:
            pose_data = self.robot_position(x, y, yaw)
            pose_topic = f"{self.robot_ip_}/pose"
            pose_payload = json.dumps(pose_data)
            self.client.publish(pose_topic, pose_payload)

            return True
        
        except:
            return False
    
    def machine_report(self, machine, x, y, yaw):
        return {
            "machine": machine,
            "x": x,
            "y": y,
            "yaw": yaw
        }
    
    def machine_report_publish(self, machine, x, y, yaw):
        try:
            report_data = self.machine_report(machine, x, y, yaw)
            report_topic = f"{self.robot_ip_}/machine_report"
            report_payload = json.dumps(report_data)
            self.client.publish(report_topic, report_payload)

            return True
        
        except:
            return False


    def mqttConnect(self):
        self.client.connect(self.mqtt_broker_address_, 1883)
        self.client.loop_start()
        
        return True
    
    def mqttDisconnect(self):
        self.client.loop_stop()
        self.client.disconnect()

        return True
    