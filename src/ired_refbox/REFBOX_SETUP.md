# REFEREE BOX Setup

## 1. Import Virtual Machines

1. Download the [Refbox Server and Bridge](https://image.raikmitl.com/index.php/s/WTOISdSI7YUpWrC) files, named "ILC-Refbox-Server" and "ILC-Refbox-Bridge".
2. Import both files into Oracle VirtualBox.

> **Note:** When importing, set the MAC address policy to "Generate new MAC address for all network adapters" and configure the network adapter as a **Bridged Adapter** for each virtual machine.

> **Recommendation:** Use a dedicated PC for easier management, with enough CPU and RAM to run the refbox comfortably.

## 2. Refbox Server Setup

1. Start the ILC-Refbox-Server VM in Oracle VirtualBox. (Password for this VM: `ilc`)
2. Open VS Code, which will already have 3 files open: `raikmitl_comm.yaml`, `local_setup.sh`, and `udp_forwarder.py`.
3. In `raikmitl_comm.yaml`, change `public-peer`'s host to the IP address of this Refbox Server VM (check with `ifconfig enp0s3`), and change `cyan-peer` and `magenta-peer`'s hosts to the IP address of the Refbox Bridge VM (check with `ifconfig enp0s3` on that VM).
   ```
       public-peer:
         # host: !ipv4 192.168.122.255
         #host: !ipv4 172.26.255.255
         host: !ipv4 192.168.0.11 # Change to IP address of ILC-Refbox-Server
         # port: !udp-port 4444
         send-port: !udp-port 4444
         recv-port: !udp-port 4445

       cyan-peer:
         # host: !ipv4 192.168.122.255
         host: !ipv4 192.168.0.12 # Change to IP address of ILC-Refbox-Bridge
         # port: !udp-port 4441
         send-port: !udp-port 4441
         recv-port: !udp-port 4446

       magenta-peer:
         # host: !ipv4 192.168.122.255
         # host: !ipv4 172.26.255.255
         host: !ipv4 192.168.0.12 # Change to IP address of ILC-Refbox-Bridge
         # port: !udp-port 4442
         send-port: !udp-port 4442
         recv-port: !udp-port 4447
   ```
4. In `local_setup.sh`, set the challenge and its difficulty by commenting/uncommenting the corresponding lines.

   Example for Navigation Challenge, hard mode:
   ```
   # Navigation Challenge
   # export REFBOX_ARGS="--cfg-challenges /etc/rcll-refbox/challenges/thopen/nav_easy.yaml --cfg-comm /etc/rcll-refbox/comm/raikmitl_comm.yaml"
   # export REFBOX_ARGS="--cfg-challenges /etc/rcll-refbox/challenges/thopen/nav_medium.yaml --cfg-comm /etc/rcll-refbox/comm/raikmitl_comm.yaml"
   export REFBOX_ARGS="--cfg-challenges /etc/rcll-refbox/challenges/thopen/nav_hard.yaml --cfg-comm /etc/rcll-refbox/comm/raikmitl_comm.yaml"
   ```

   Example for Exploration Challenge:
   ```
   # Exploration Challenge
   export REFBOX_ARGS="--cfg-challenges /etc/rcll-refbox/challenges/exp/exploration_easy.yaml --cfg-comm /etc/rcll-refbox/comm/raikmitl_comm.yaml"
   ```
5. In `udp_forwarder.py`, change the IP addresses in `DESTINATIONS` to the Refbox Bridge address.
   ```
   # Destination computers
   DESTINATIONS = [
       ("192.168.0.12", 4500),  # Change to IP address of ILC-Refbox-Bridge
       ("192.168.0.12", 4501)   # Change to IP address of ILC-Refbox-Bridge
   ]
   ```
6. Set up and start the refbox.

   > **Note:** Run the following commands from the `~/rcll-get-started/` directory.
   ```
   cd ~/rcll-get-started/
   ```
   Update configuration:
   ```
   source setup.sh
   ```
   Start the refbox:
   ```
   rc_start
   ```
   Stop the refbox:
   ```
   rc_stop
   ```
7. After starting the refbox, start the port forwarder so data reaches the ILC-Refbox-Bridge:
   ```
   cd ~/rcll-relay-server
   docker compose up
   ```

## 3. Refbox Bridge Setup

1. Start the ILC-Refbox-Bridge VM in Oracle VirtualBox. (Password for this VM: `ilc`)
2. Open VS Code, which will already have 3 files open: `.env`, `mqtt_forward.py`, and `robot_pub.py`.
3. In `.env`, change `RC_MQTT_REFBOX` to the IP address of the ILC-Refbox-Server.
   ```
   RC_MQTT_REFBOX=192.168.0.11 # Change to IP address of ILC-Refbox-Server
   ```
4. In `mqtt_forward.py`, change the `CYAN` entry in `TEAM_MAPPING` to your robot's IP address (check with `ifconfig wlan0`).
   ```
   TEAM_MAPPING = {
       "MAGENTA":"172.16.0.216" ,
       "CYAN":"172.16.0.211"       # Your robot IP address
   }
   ```
5. `robot_pub.py` is an example script showing how to send test data to the refbox.
6. Start the MQTT bridge to the robot:
   ```
   cd ~/thopen-refbox-bridge/
   docker compose up
   ```

## 4. Refbox Frontend Setup

1. Open the website at `http://<ILC-Refbox-Server-IP>:8080/`, for example `http://192.168.0.11:8080/`.
2. Press `Ctrl+Alt+O` to open the referee configuration, then click **Connect**.
3. Set up the Cyan and Magenta teams.
4. In the config menu, change `/llsfrb/globals/setup-time` to `120` and `/llsfrb/globals/production-time` to `600`, per the rulebook for mobile robot competitions.
5. Click **Start Game** to begin.
6. Click **Watch** to monitor the field.
