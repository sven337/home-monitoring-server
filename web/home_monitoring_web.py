from functools import wraps
import rrdtool
import os
from flask import Flask, abort, request, url_for, render_template
app = Flask(__name__)

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
last_temperature = -1.0

def report_temperature(temp):
	global last_temperature
	last_temperature = float(temp)
	rrdtool.update(rrdfile("temperature"), "N:" + str(temp))
	return "Updated temperature to " + str(temp)

last_gas_index = -1
last_gas_pulse = -1

def write_gas_index(idx):
	index_file = open(rrdfile("gas_last_index")[0:-3] + "txt", 'w')
	index_file.write(str(idx))
	index_file.close()


def report_gas_pulse(pulse):
	global last_gas_index
	global last_gas_pulse
	# Retrieve previous gas index if we do not know it
	if last_gas_index == -1:
		# RRD doesn't easily give this information so read it from a file instead!
		index_file = open(rrdfile("gas_last_index")[0:-3] + "txt")
		last_gas_index = float(index_file.read())

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
	return "Got pulse " + str(pulse) + ", computed gas index " + str(last_gas_index)

def report_gas_index(idx):
	global last_gas_index
	global last_gas_pulse
	last_gas_index = idx
	write_gas_index(idx)
	rrdtool.update(rrdfile("gas"), "N:" + str(last_gas_pulse) + ":" + str(last_gas_index))
	return "Set gas index to " + str(last_gas_index)

def report_elec(pwr, idx):
	global last_electricity_power
	last_electricity_power = int(pwr)
	rrdtool.update(rrdfile("edf"), "N:" + str(pwr) + ":" + str(idx))
	return "Reported electricity power " + str(pwr) + ", index " + str(idx)


@app.route("/update/<feed_class>/<feed_data>")
@app.route("/update/<feed_class>/<feed_field>/<feed_data>")
#@admin_required
def update(feed_class,feed_data,feed_field=""):
	if feed_class == "temperature":
		return report_temperature(float(feed_data))
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
	else:
   		return "Unknown feed class", 500

@app.route("/render_graphs")
#@key_required
def render_graphs():
	os.system("cd ../rrd; ./rrd_render_graphs.sh")
	return "Done"


@app.route("/last/<feed_class>/")
#@key_required
def last(feed_class):
	if feed_class == "temperature":
		return str(last_temperature)
	elif feed_class == "gas":
		return str(last_gas_index) + "," + str(last_gas_pulse)
	elif feed_class == "electricity":
		return str(last_electricity_power)
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
	return render_template('rrdJFlot.html', rrdfile="/rrd/" + feed_class + "?api_key=eb5bb384-2d0b-4a2e-abe1-3f6abb564619")
