#!/usr/bin/python2

import sys
import rrdtool

APIKEY=""
RRD_PATH=""

def read_vars(path):
	global RRD_PATH
	config=open(path)
	for line in config.readlines():
		splt = line.split('=')
		if splt[0] == 'APIKEY':
			APIKEY=splt[1].strip("\n")
		if splt[0] == 'RRD_PATH':
			RRD_PATH=splt[1].strip("\n")

read_vars("rrd_config.rc")
print(RRD_PATH)
data=sys.stdin.readlines()
linenb=0

if len(sys.argv) < 2:
	print("Usage: " + sys.argv[0] + " <rrd_file.rrd>")
	sys.exit(1)

for line in data:
	line=line.strip("\n")
	if linenb % 1024 == 0:
		print("Line " + str(linenb))
	try: 
		rrdtool.update(RRD_PATH + '/' + sys.argv[1], line)
	except:
		print("Update line " + str(linenb) + " failed")
	linenb = linenb+1
