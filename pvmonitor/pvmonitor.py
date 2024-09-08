#!/usr/bin/python

from datetime import datetime, timezone
import pytz
from pysolar import solar
from configparser import ConfigParser
import paho.mqtt.client as mqtt
import json
from http.server import BaseHTTPRequestHandler, HTTPServer
import threading
import subprocess
import copy

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

class LongTermAverageUpdater:
    def __init__(self, ratios, smoothing_factor=0.001):
        self.smoothing_factor = smoothing_factor
        self.ratios = copy.deepcopy(ratios)

    def update_ratios(self, inverter_id, panel_number, new_ratio):
        if inverter_id not in self.ratios:
            self.ratios[inverter_id] = {}

        if panel_number not in self.ratios[inverter_id]:
            self.ratios[inverter_id][panel_number] = new_ratio
        else:
            current_average = self.ratios[inverter_id][panel_number]
            updated_average = (self.smoothing_factor * new_ratio +
                              (1 - self.smoothing_factor) * current_average)
            self.ratios[inverter_id][panel_number] = updated_average


initial_ratios = {
    "116183124575": {1: 0.244, 2: 0.248, 3: 0.262, 4: 0.246},
    "116184895965": {1: 0.331, 2: 0.336, 3: 0.333, 4: 0} # No 4th panel on this inverter
}

long_term_averages = LongTermAverageUpdater(initial_ratios, smoothing_factor=0.05)

current_frame_inverter_id = None

system_status = "Starting up"


def get_sun_position():
    date = datetime.now(timezone.utc)
    altitude = solar.get_altitude(LATITUDE, LONGITUDE, date)
    azimuth = solar.get_azimuth(LATITUDE, LONGITUDE, date)
    return altitude, azimuth

def is_shadow_expected(panel_id, panel_number):
    altitude, azimuth = get_sun_position()
    # Implement logic to determine if shadow is expected based on sun position and panel location
    # This is a placeholder and should be customized based on your specific setup
    if altitude < 10:  # Sun is low in the sky
        return True
    return False

def check_panel_ratios(inverter_id):
    global system_status, last_anomaly_time
    panels = panel_data[inverter_id]

    # Bail if we do not have data
    if 0 not in panels:
        return

    total_power = panels[0]
    if total_power == 0:
        return
        
    current_time = datetime.now().astimezone().isoformat()

    print(f"\n{current_time} Ratios for Inverter {inverter_id}:")
    print("Panel | Current Ratio | Expected Ratio | Delta")
    print("-----------------------------------------")

    abnormal_panels = []
    for panel_number, power in panels.items():
        # Skip total entry
        if panel_number == 0:
            continue

        actual_ratio = power / total_power
        long_term_averages.update_ratios(inverter_id, panel_number, actual_ratio)
        expected_ratio = long_term_averages.ratios[inverter_id][panel_number]
        delta = actual_ratio - expected_ratio
    
        print(f"{panel_number:>5} | {actual_ratio:>13.2%} | {expected_ratio:>14.2%} | {delta:>6.1%}")

        if abs(delta) > 0.1 and not is_shadow_expected(inverter_id, panel_number):
            abnormal_panels.append(f"Inverter {inverter_id}, Panel {panel_number}")
            print(f"Abnormal pattern detected at {current_time}: Inverter {inverter_id}, Panel {panel_number}")
            print(f"Expected ratio: {expected_ratio:.2f}, Actual ratio: {actual_ratio:.2f}")
            print(str(json.dumps(panel_data)))

    if abnormal_panels:
        system_status = f"Abnormal patterns detected: {', '.join(abnormal_panels)}"

        # Check the time since the last anomaly notification
        current_time = datetime.now()
        if last_anomaly_time is None or (current_time - last_anomaly_time).total_seconds() > 1800:
            # Call the notification script
            process = subprocess.Popen(['bash', 'pvmonitor_notify_anomaly.sh'], stdin=subprocess.PIPE)
            process.communicate(input=system_status.encode())
            last_anomaly_time = current_time
    else:
        system_status = "All panels operating normally"

def on_connect(client, userdata, flags, rc):
    print("Connected with result code "+str(rc))
    client.subscribe("solar/+/+/power")
    client.subscribe("solar/+/0/powerdc")

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


class SolarPanelHTTPHandler(BaseHTTPRequestHandler):

    def convert_ratios_to_percentages(self, ratio_dict):
        percentages = {}
        for inverter, panels in ratio_dict.items():
            percentages[inverter] = {panel: "%.0f%%" % (round(ratio * 100, 2)) for panel, ratio in panels.items()}
        return percentages

    def do_GET(self):
        if self.path == '/':
            self.send_response(200)
            self.send_header('Content-type', 'application/json')
            self.end_headers()

            # Convert long-term averages to percentages
            long_term_percentages = self.convert_ratios_to_percentages(long_term_averages.ratios)

            global initial_ratios

            response = {
                'status': system_status,
                'panel_data': panel_data,
                'long_term_averages': long_term_percentages,
                'initial_ratios' : self.convert_ratios_to_percentages(initial_ratios)
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
