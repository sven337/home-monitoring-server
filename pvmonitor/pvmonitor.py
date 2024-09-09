#!/usr/bin/python

from datetime import datetime, timezone
import pytz
#from pysolar import solar
from configparser import ConfigParser
import paho.mqtt.client as mqtt
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import subprocess
import copy
import io
import sys

# When is the last time an anomaly was reported (for rate limiting)
last_anomaly_time = None

# Read the configuration file
config = ConfigParser()
config.read('pvmonitor.cfg')

MQTT_SERVER = config.get('MQTT', 'server')
MQTT_PORT = config.getint('MQTT', 'port')
MQTT_USER = config.get('MQTT', 'user')
MQTT_PASSWORD = config.get('MQTT', 'password')

LATITUDE = config.getfloat('LOCATION', 'latitude')
LONGITUDE = config.getfloat('LOCATION', 'longitude')

panel_data = {}
total_yields = {}

current_frame_inverter_id = None

system_status = "Starting up"


def check_panel_ratios(inverter_id):
    global system_status, last_anomaly_time
    panels = panel_data[inverter_id]
    yields = total_yields[inverter_id]

    # Bail if we do not have data
    if 0 not in panels or 0 not in yields:
        return

    total_power = panels[0]
    # If total inverter power is less than 40W, then ignore: this is the start
    # or stop time, things are expected to be not ideal.
    if total_power < 40:
        return
        
    current_time = datetime.now().astimezone().isoformat()

    # Capture the table output
    output = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = output

    print(f"\n{current_time} Ratios for Inverter {inverter_id}:")
    print("Panel | Current Ratio | Expected Ratio | Delta")
    print("-----------------------------------------")

    abnormal_panels = []
    for panel_number, power in panels.items():
        # Skip total entry
        if panel_number == 0:
            continue

        actual_ratio = power / total_power
        expected_ratio = yields[panel_number] / yields[0]
        delta = actual_ratio - expected_ratio
    
        print(f"{panel_number:>5} | {actual_ratio:>13.1%} | {expected_ratio:>14.1%} | {delta:>6.1%}")

        if abs(delta) > 0.05:
            abnormal_panels.append(f"Inverter {inverter_id}, Panel {panel_number}")
            print(f"Abnormal pattern detected at {current_time}: Inverter {inverter_id}, Panel {panel_number}")
            print(f"Expected ratio: {expected_ratio:.2f}, Actual ratio: {actual_ratio:.2f}")

    # Restore stdout and get the captured output
    sys.stdout = original_stdout
    table_output = output.getvalue()
    
    # Print the table to console
    print(table_output)

    if abnormal_panels:
        system_status = f"Abnormal patterns detected: {', '.join(abnormal_panels)}"

        # Check the time since the last anomaly notification
        current_time = datetime.now()
        if last_anomaly_time is None or (current_time - last_anomaly_time).total_seconds() > 1800:
            # Prepare the full message including the table and system status
            full_message = f"{table_output}\n\n{system_status}\n\nPanel Data: {json.dumps(panel_data, indent=2)}"
            
            # Call the notification script with the full message
            process = subprocess.Popen(['bash', 'pvmonitor_notify_anomaly.sh'], stdin=subprocess.PIPE)
            process.communicate(input=full_message.encode())
            last_anomaly_time = current_time
    else:
        system_status = "All panels operating normally"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    client.subscribe("solar/+/+/power")
    client.subscribe("solar/+/0/powerdc")
    client.subscribe("solar/+/+/yieldtotal")

def on_message(client, userdata, msg):
    # We receive MQTT messages one by one, but we can only work based on
    # "frames", that is, complete update of powerdc for the inverter + power
    # values for each panel connected to it.
    # OpenDTU emits the data in that order:
    # --- start of frame
    # sept. 08 18:36:18 solar/116183124575/0/powerdc 289.0
    # sept. 08 18:36:18 solar/116183124575/0/power 274.6
    # sept. 08 18:36:19 solar/116183124575/1/power 50.5
    # sept. 08 18:36:19 solar/116183124575/2/power 78.1
    # sept. 08 18:36:19 solar/116183124575/3/power 83.6
    # sept. 08 18:36:19 solar/116183124575/4/power 76.8
    # --- start of frame
    # sept. 08 18:36:19 solar/116184895965/0/powerdc 292.7
    # sept. 08 18:36:19 solar/116184895965/0/power 278.1
    # sept. 08 18:36:19 solar/116184895965/1/power 94.7
    # sept. 08 18:36:19 solar/116184895965/2/power 96.5
    # sept. 08 18:36:19 solar/116184895965/3/power 101.2
    # sept. 08 18:36:19 solar/116184895965/4/power 0.3


    topic_parts = msg.topic.split('/')
    inverter_id = topic_parts[1]
    panel_number = int(topic_parts[2])
    power_type = topic_parts[3]
    power = float(msg.payload)

    if inverter_id not in panel_data:
        panel_data[inverter_id] = {}
        total_yields[inverter_id] = {}

    if power_type == "powerdc":
        # Start of a new frame
        # Handle the previous frame: we can check ratios now
        global current_frame_inverter_id
        if current_frame_inverter_id:
            check_panel_ratios(current_frame_inverter_id)

        panel_data[inverter_id][0] = power
        current_frame_inverter_id = inverter_id

    elif power_type == "power" and panel_number > 0:
        panel_data[inverter_id][panel_number] = power
    elif power_type == "yieldtotal":
        total_yields[inverter_id][panel_number] = power


class SolarPanelHTTPHandler(BaseHTTPRequestHandler):

    def convert_yields_to_percentages(self, yields_dict):
        percentages = {}
        for inverter, panels in yields_dict.items():
            percentages[inverter] = {panel: "%.0f%%" % (round(totalyield / panels[0] * 100, 2)) for panel, totalyield in panels.items()}
        return percentages

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            # Convert long-term averages to percentages
            long_term_percentages = self.convert_yields_to_percentages(total_yields)

            response = {
                'status': system_status,
                'panel_data': panel_data,
                'total_yields_pct': long_term_percentages,
            }

            self.wfile.write(json.dumps(response, indent=2).encode())

class SimpleWebInterface:
    def __init__(self, port):
        self.server_address = ('', port)
        self.httpd = HTTPServer(self.server_address, SolarPanelHTTPHandler)

    def start(self):
        print(f'Serving on port {self.server_address[1]}...')
        self.httpd.serve_forever()

def start_web_server():
    web_interface = SimpleWebInterface(port=9090)
    web_interface.start()

# Start MQTT client
client = mqtt.Client()
client.username_pw_set(MQTT_USER, MQTT_PASSWORD)
client.on_connect = on_connect
client.on_message = on_message

client.connect(MQTT_SERVER, MQTT_PORT, 60)

# Start web server in a separate thread
web_thread = threading.Thread(target=start_web_server)
web_thread.start()

# Start MQTT loop
client.loop_forever()
