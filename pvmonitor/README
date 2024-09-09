# PVMonitor

This script monitors an [OpenDTU](https://github.com/tbnobody/OpenDTU/)-based solar installation to check for abnormal production patterns.

## Features

- Connects to MQTT broker to receive solar panel data
- Monitors multiple inverters and their connected panels
- Calculates and compares panel performance ratios
- Detects abnormal patterns in panel output

## Requirements

- Python 3.x
- MQTT broker (e.g., Mosquitto)
- Required Python packages: paho-mqtt, pytz, configparser

## Configuration

Create a `pvmonitor.cfg` file in the same directory as the script with the following structure:

```ini
[MQTT]
server = your_mqtt_server
port = 1883
user = your_mqtt_username
password = your_mqtt_password
```

## Debug Web Interface

Most logs go to the console, but you can also use access `http://localhost:9090` for real-time status.

## Anomaly Detection

The program detects abnormal patterns by comparing each panel's current power ratio to its expected ratio based on total historical yield. If the difference exceeds 5%, it's flagged as abnormal.

## Notifications

Provide a `pvmonitor_notify_anomaly.sh` script. It gets passed the message as input. Mine simply sends an e-mail.

