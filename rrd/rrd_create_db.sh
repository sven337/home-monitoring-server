#!/bin/bash

source rrd_config.rc
OVERWRITE="--no-overwrite"

if [ $1 = "--overwrite" ]; then
	OVERWRITE=""
fi

# Create temperature
# 300 seconds = 5 minutes interval
# Keep 	5 minute-data for two days
#		15 minute-data for a week
#		1 day data for a year
#		14 day data for five years

echo Creating temperature.rrd
rrdcreate $RRD_PATH/temperature.rrd --start 20130607 --step 300 $OVERWRITE "DS:TEMPERATURE:GAUGE:7200:10:40" \
			  "RRA:AVERAGE:0.5:1:576" \
			  "RRA:AVERAGE:0.5:3:672" \
			  "RRA:AVERAGE:0.5:288:370" \
			  "RRA:AVERAGE:0.5:4032:130" \
			  "RRA:MIN:0.5:288:370" \
			  "RRA:MIN:0.5:4032:130" \
			  "RRA:MAX:0.5:288:370" \
			  "RRA:MAX:0.5:4032:130" 

# Create electricity (power and index)
# 1 minute interval
# Keep 1 minute-data for a day
# Keep 1 hour data for a week
# Keep 1 day data for two years
# Input is: power as given by the meter, kwh (= counter value) as given by the meter. This is redundant but ensures real values.
echo Creating edf.rrd
rrdcreate $RRD_PATH/edf.rrd  --start 20130607 --step 60 $OVERWRITE "DS:ELEC_POWER:GAUGE:600:0:12000" "DS:ELEC_KWH:DERIVE:600:0:1" \
			  "RRA:AVERAGE:0.99:1:1440" \
			  "RRA:AVERAGE:0.99:60:168" \
			  "RRA:AVERAGE:0.99:1440:720" \
			  "RRA:MIN:0.99:1440:720" \
			  "RRA:MAX:0.99:1440:720" 


# Create gas - same parameters exactly
# Input is: pulse counter as given by DIY electronics. May reset randomly, min/max values are set to avoid these events.
#			index base is the current base (starting point) for the meter. Use it for adjustments when needed.
echo Creating gas.rrd
rrdcreate $RRD_PATH/gas.rrd  --start 20130607 --step 60 $OVERWRITE "DS:GAS_PULSE:DERIVE:2592000:0:100" "DS:GAS_IDX:GAUGE:2592000:0:U" \
			  "RRA:AVERAGE:0.99:1:1440" \
			  "RRA:AVERAGE:0.99:60:168" \
			  "RRA:AVERAGE:0.99:1440:720" \
			  "RRA:MIN:0.99:1440:720" \
			  "RRA:MAX:0.99:1440:720" 
