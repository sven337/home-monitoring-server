#!/bin/bash

source rrd_config.rc

if [ $# -eq 0 ]; then
	echo "Usage: $0 <rrd_database>"
	exit 1
fi

while read line; do
	echo rrdtool update $RRD_PATH/$1 $line
	rrdtool update $RRD_PATH/$1 $line
done
