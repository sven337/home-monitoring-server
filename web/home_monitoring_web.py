from functools import wraps
import rrdtool
import os
import time
import logging
from datetime import datetime
from flask import Flask, abort, request, url_for, render_template
app = Flask(__name__)

#log = logging.getLogger('werkzeug')
#log.setLevel(logging.WARNING)

app.config.from_object('default_settings')
try:
	app.config.from_envvar('HOME_MONITORING_SERVER_SETTINGS')
except:
	pass

def key_required(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		key = request.args.get('api_key')
		if key not in app.config['HOME_MONITORING_SERVER_API_KEYS']:
			return 'invalid api_key', 403
		return f(*args, **kwargs)
	return decorated_function

def admin_required(f):
	@wraps(f)
	def decorated_function(*args, **kwargs):
		key = request.args.get('admin_key')
		required_key = app.config['HOME_MONITORING_SERVER_ADMIN_KEY']
		if required_key and key != required_key:
			return 'invalid admin_key', 403
		return f(*args, **kwargs)
	return decorated_function


@app.route('/')
def root():
	"""Root url"""
	return "Nothing to see here..."

@app.route('/status')
def status():
	"""Status page. Returns "ok" if it works."""
	return "ok"

def rrdfile(name):
	return app.config['RRD_PATH'] + '/' + name + ".rrd"

last_electricity_power = -1
last_temperature = { 'pantry' : 20.0, 'officeAH' : 21.0, 'exterior' : 19.0, 'living' : 19.0, 'bed' : 19.0 }
last_temperature_date = { 'pantry' : datetime(2014, 12, 31), 'officeAH' : datetime(2014, 12, 31), 'exterior' : datetime(2014, 12, 31), 'living' : datetime(2015, 12, 01), 'bed' : datetime(2015, 12, 01) }
last_battery_level = { 'exterior_thermometer' : 0, 'mailbox' : 0, 'gas' : 0 }
last_battery_level_date = { 'exterior_thermometer' : datetime(2014, 12, 31), 'mailbox' : datetime(2014, 12, 31), 'gas' : datetime(2014, 12, 31) }

def report_temperature(name, temp):
	global last_temperature
	last_temperature[name] = float(temp)
	last_temperature_date[name] = datetime.now()
	rrdtool.update(rrdfile("temperature_"+name), "N:" + str(temp))
	return "Updated " + name + " temperature to " + str(temp)

last_gas_index = -1
last_gas_pulse = -1

def write_gas_index(idx):
	index_file = open(rrdfile("gas_last_index")[0:-3] + "txt", 'w')
	index_file.write(str(idx))
	index_file.close()

def report_battery_level(name, percentage):
	global last_battery_level
	batlevel = open(rrdfile("battery_level_" + name)[0:-3] + "txt", 'a')
	batlevel.write(time.strftime("%Y-%m-%d %H:%M:%S\t") + str(percentage) + "%\n")
	batlevel.close();
	last_battery_level[name] = percentage
	last_battery_level_date[name] = datetime.now()
	if percentage < 15:
		os.system("mail root -s  'Low battery for " + name + ": " + percentage)
	return "Recorded battery level for " + name + " at " + str(percentage) + "%\n"


def report_gas_pulse(pulse):
	global last_gas_index
	global last_gas_pulse
	# Retrieve previous gas index if we do not know it
	if last_gas_index == -1:
		# RRD doesn't easily give this information so read it from a file instead!
		index_file = open(rrdfile("gas_last_index")[0:-3] + "txt")
		last_gas_index = float(index_file.read())
		index_file.close()

	# If we do not know the previous pulse counter value, there is nothing we can do, 
	# so just ignore this update
	if last_gas_pulse == -1:
		last_gas_pulse = pulse

	# If pulse counter was reset, don't add anything
	if pulse < last_gas_pulse:
		last_gas_pulse = pulse 

	last_gas_index = last_gas_index + (pulse - last_gas_pulse) / 100.0
	write_gas_index(last_gas_index)
	last_gas_pulse = pulse

	rrdtool.update(rrdfile("gas"), "N:" + str(pulse) + ":" + str(last_gas_index))
	return "Got pulse " + str(pulse) + ", computed gas index " + str(last_gas_index) + "\n"

def report_gas_index(idx):
	global last_gas_index
	global last_gas_pulse
	last_gas_index = idx
	write_gas_index(idx)
	rrdtool.update(rrdfile("gas"), "N:" + str(last_gas_pulse) + ":" + str(last_gas_index))
	return "Set gas index to " + str(last_gas_index) + "\n"

def report_elec(pwr, idx):
	global last_electricity_power
	last_electricity_power = int(pwr)
	if (last_electricity_power >= 6500):
		os.system("cd ../power_warning; ./warn_power.sh " + str(last_electricity_power))
		
	rrdtool.update(rrdfile("edf"), "N:" + str(pwr) + ":" + str(idx))
	return "Reported electricity power " + str(pwr) + ", index " + str(idx) + "\n"

def report_humidity(name, percentage):
	return "Ignoring reported humidity for " + str(name) + "=" + str(percentage) + "\n"

@app.route("/update/<feed_class>/<feed_data>")
@app.route("/update/<feed_class>/<feed_field>/<feed_data>")
#@admin_required
def update(feed_class,feed_data,feed_field=""):
	if feed_class == "temperature":
		if feed_field not in [ "pantry", "officeAH", "exterior", "living", "bed" ]:
			return "Must specify valid thermometer location (pantry, officeAH, exterior, living, bed)"
	
		return report_temperature(str(feed_field), float(feed_data))
	elif feed_class == "gas":
		if feed_field == "pulse":
			return report_gas_pulse(int(feed_data))
		elif feed_field == "set_index":
			return report_gas_index(float(feed_data))
		else:
	   		return "Must use \"pulse\" or \"set_index\"", 500
	elif feed_class == "electricity":
		elec_data = feed_data.split(',')
		return report_elec(float(elec_data[0]), int(elec_data[1]))
	elif feed_class == "battery_level":
		if feed_field == "":
			return "Must specify name of device for battery level report (free form)"
		return report_battery_level(feed_field, int(feed_data))
	elif feed_class == "humidity":
		if feed_field == "":
			return "Must specify hygrometer location (pantry, officeAH, exterior)"
		return report_humidity(feed_field, int(feed_data));
	else:
   		return "Unknown feed class", 500

@app.route("/render_graphs")
#@key_required
def render_graphs():
	os.system("cd ../rrd; ./rrd_render_graphs.sh")
	return "Done"


@app.route("/last/<feed_class>/")
@app.route("/last/<feed_class>/<feed_field>")
#@key_required
def last(feed_class, feed_field=""):
	if feed_class == "temperature":
		if feed_field == "":
			return str(last_temperature) + str(last_temperature_date)
		else:
			updated_last = (datetime.now() - last_temperature_date[feed_field]).total_seconds()
			if updated_last > 3600:
				return "OLD"
			else:
				return str(last_temperature[feed_field])
	elif feed_class == "gas":
		return str(last_gas_index) + "," + str(last_gas_pulse)
	elif feed_class == "electricity":
		return str(last_electricity_power)
	elif feed_class == "battery_level":
		if feed_field == "":
			return str(last_battery_level)
		else:
		   	return str(last_battery_level[feed_field])
	else:
   		return "Unknown feed class", 500

@app.route("/rrd/<feed_class>/")
#@key_required
def get_rrd_file(feed_class):
	f = open(rrdfile(feed_class))
	data = f.read()
	f.close()
	return data

@app.route("/graph/<feed_class>")
#@key_required
def show_graphs(feed_class=""):
	#not working
	return render_template('rrdJFlot.html', rrdfile="/rrd/" + feed_class)
