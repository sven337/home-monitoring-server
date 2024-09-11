#!/usr/bin/python

from datetime import datetime, timezone, timedelta
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
from pysolar import solar  
import pytz
import pickle 

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


abnormal_panel_start_times = {}

pivot_tables = None
std_dev_tables = None
elevation_bins = None
azimuth_bins = None

def load_sun_position_data():
    with open('history/panel_historical_ratios_from_sun_position.pkl', 'rb') as f:
        data = pickle.load(f)
    return data['pivot_tables'], data['std_dev_tables'], data['elevation_bins'], data['azimuth_bins']


def estimate_ratio(ratio_column, sun_elevation, sun_azimuth):
    global pivot_tables, std_dev_tables, elevation_bins, azimuth_bins

    if not pivot_tables:
        pivot_tables, std_dev_tables, elevation_bins, azimuth_bins = load_sun_position_data()

    if not pivot_tables:
        print("No data")
        return

    if not ratio_column in pivot_tables:
        return None, None

    #print(f"Estimating ratio for {ratio_column}, sun elv {sun_elevation} azm {sun_azimuth}")
    # Find the correct elevation and azimuth buckets
    elevation_label = None
    azimuth_label = None

    for i, interval in enumerate(elevation_bins.cat.categories):
        if interval.left <= sun_elevation <= interval.right:
            elevation_label = f'E{i+1}: {interval.left:.1f}°-{interval.right:.1f}°'
            break

    for i, interval in enumerate(azimuth_bins.cat.categories):
        if interval.left <= sun_azimuth <= interval.right:
            azimuth_label = f'A{i+1}: {interval.left:.1f}°-{interval.right:.1f}°'
            break

    if elevation_label is None or azimuth_label is None:
        raise ValueError("Sun elevation or azimuth is outside the range of the bins")

    # Lookup the ratio and standard deviation
    expected_ratio = pivot_tables[ratio_column].loc[elevation_label, azimuth_label]
    std_dev = std_dev_tables[ratio_column].loc[elevation_label, azimuth_label]

    #print(f"--> {expected_ratio} {std_dev}")
    return expected_ratio, std_dev
    
def get_sun_position():
    date = datetime.now().astimezone()
    altitude = solar.get_altitude(LATITUDE, LONGITUDE, date)
    azimuth = solar.get_azimuth(LATITUDE, LONGITUDE, date)
    return altitude, azimuth
    

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
        
    current_time = datetime.now().astimezone()

    # Capture the table output
    output = io.StringIO()
    original_stdout = sys.stdout
    sys.stdout = output

    print(f"\n{current_time.isoformat(' ', timespec='minutes')} Ratios for Inverter {inverter_id}:")
    print("Panel | Current Ratio | Expected Ratio | Err Threshold | Delta")
    print("-----------------------------------------")

    for panel_number, power in panels.items():
        # Skip total entry
        if panel_number == 0:
            continue

        actual_ratio = power / total_power
        inverter_name_to_id = { '116183124575' : '1', '116184895965' : '2' }
        expected_ratio, threshold = (None, None)

        if inverter_id in inverter_name_to_id:
            e, a = get_sun_position()
            expected_ratio, stdev = estimate_ratio(inverter_name_to_id[inverter_id] + 'p' + str(panel_number) + '_ratio', e, a)
            threshold = 2*stdev if stdev else None

        if not expected_ratio:
            if not inverter_id == '116184895965' and panel_number == 4:
                # That particular panel isn't connected and so isn't in the history
                print(f"Ratio estimation for panel {panel_number} inverter {inverter_id} came back None, using long term avg")
            expected_ratio = yields[panel_number] / yields[0]
            threshold = 0.05

        delta = actual_ratio - expected_ratio
    
        
        panel_key = f"{inverter_id} panel {panel_number}"
        panel_abnormal = False
        if abs(delta) > threshold:
            if panel_key not in abnormal_panel_start_times:
                abnormal_panel_start_times[panel_key] = current_time

            panel_abnormal = True
            print(f"Abnormal pattern detected at {current_time.isoformat(' ', timespec='minutes')}: Inverter {inverter_id}, Panel {panel_number}")
            print(f"Expected ratio: {expected_ratio:.2f} +- {threshold}, Actual ratio: {actual_ratio:.2f}")
        else:
            if panel_key in abnormal_panel_start_times:
                del abnormal_panel_start_times[panel_key]

        print(f"{panel_number:>5} | {actual_ratio:>13.1%} | {expected_ratio:>14.1%} | {threshold:>13.1%} | {delta:>6.1%}{'<<<<<---' if panel_abnormal else ''}")

    # Restore stdout and get the captured output
    sys.stdout = original_stdout
    table_output = output.getvalue()
    
    # Print the table to console
    print(table_output)

    send_notification = False
    if len(abnormal_panel_start_times) > 0:
        system_status = "Abnormal panels"

    for panel_key, abnormal_since in abnormal_panel_start_times.items():
        anomaly_duration = current_time - abnormal_since
        system_status += f"{panel_key} for {anomaly_duration.total_seconds() / 60:.0f} minutes\n"
#        if anomaly_duration >= timedelta(minutes=10):
        if anomaly_duration >= timedelta(minutes=1):
            # This panel has been wrong for more than 10 minutes, notify
            send_notification = True

    if send_notification:
        # Check the time since the last anomaly notification
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
