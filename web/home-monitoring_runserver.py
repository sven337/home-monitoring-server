#!/usr/bin/python

from home_monitoring_web import app
import os
os.environ['HOME_MONITORING_SERVER_SETTINGS'] = os.environ['HOME'] + '/.home-monitoring-server_settings'
app.run(debug=True, threaded=True, host="0.0.0.0")
