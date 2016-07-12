#!/bin/bash

source rrd_config.rc

WIDTH="--width 700"
HEIGHT="--height 250"
LABEL="--vertical-label" 

graph_temperature()
{
	echo Rendering $1
	for where in officeAH pantry exterior living bed; do
		rrdtool graph $GRAPH_PATH/$1_${where}.png --width 800 --height 400 --vertical-label °C --start $2 \
				"DEF:temp=$RRD_PATH/temperature_${where}.rrd:TEMPERATURE:AVERAGE" \
				"VDEF:max=temp,MAXIMUM" \
				"VDEF:min=temp,MINIMUM" \
				"LINE2:temp#FF3F00:Température" \
				"HRULE:max#FF0000:Max" \
				"HRULE:min#0000FF:Min" \
				"GPRINT:max:Max %2.1lf °C" "GPRINT:max:le %d/%M/%y:strftime" \
				"GPRINT:min:Min %2.1lf °C" "GPRINT:min:le %d/%M/%y:strftime"
#			"VDEF:slope=temp,LSLSLOPE" "VDEF:inter=temp,LSLINT" \
#			"GPRINT:slope:Var %2.1lf %s°C/heure"
	done
			
}

graph_edf()
{
	echo Rendering $1
	rrdtool graph $GRAPH_PATH/$1_power.png --width 800 --height 400 --vertical-label W --start $2 \
		"DEF:power=$RRD_PATH/edf.rrd:ELEC_POWER:AVERAGE" \
		"DEF:kwh=$RRD_PATH/edf.rrd:ELEC_KWH:AVERAGE" \
		"AREA:power#000000:Puissance" \
		"CDEF:eurovect=kwh,0.1329,*" \
		"VDEF:euro=eurovect,TOTAL" \
		"VDEF:total=kwh,TOTAL" \
		"GPRINT:total:Total %3.1lf kWh" "GPRINT:euro:%4lf EUR"
}

graph_gas()
{
	echo Rendering $1
	rrdtool graph $GRAPH_PATH/$1_gas.png --width 800 --height 400 --vertical-label W --start $2 \
		"DEF:idx=$RRD_PATH/gas.rrd:GAS_IDX:MAX" \
		"DEF:pulse=$RRD_PATH/gas.rrd:GAS_PULSE:AVERAGE" \
		"CDEF:kwh=pulse,0.1082,*" \
		"CDEF:power=kwh,3600000,*" \
		"AREA:power#000000:Puissance gaz" \
		"CDEF:eurovect=kwh,0.0576,*" \
		"VDEF:euro=eurovect,TOTAL" \
		"VDEF:total=kwh,TOTAL" \
		"GPRINT:total:Total %3.1lf kWh" "GPRINT:euro:%4lf EUR" \
		"VDEF:index=idx,LAST" \
		"GPRINT:index:Indice compteur %4.2lf"
}

export_temperature()
{
	MAXROWS="$4"
	if [ -z "$MAXROWS" ]; then
		MAXROWS=700
	fi
	echo Exporting $1
	
	for where in officeAH pantry exterior living bed; do
		rrdtool xport --maxrows $MAXROWS --start $2  --end $3\
				"DEF:temp=$RRD_PATH/temperature_${where}.rrd:TEMPERATURE:AVERAGE" \
				"XPORT:temp:Temperature"\
				> $GRAPH_PATH/$1_${where}.xml
	done
}

export_edf()
{
	MAXROWS="$4"
	if [ -z "$MAXROWS" ]; then
		MAXROWS=700
	fi
	echo Exporting $1
	rrdtool xport --maxrows $MAXROWS --start $2 --end $3\
		"DEF:power=$RRD_PATH/edf.rrd:ELEC_POWER:AVERAGE" \
		"XPORT:power:Puissance"\
		 > $GRAPH_PATH/$1.xml
}

export_gas()
{
	echo Exporting $1
	MAXROWS="$4"
	if [ -z "$MAXROWS" ]; then
		MAXROWS=700
	fi
	rrdtool xport --maxrows $MAXROWS --start $2 --end $3 \
		"DEF:idx=$RRD_PATH/gas.rrd:GAS_IDX:MAX" \
		"DEF:pulse=$RRD_PATH/gas.rrd:GAS_PULSE:AVERAGE" \
		"CDEF:kwh=pulse,0.1082,*" \
		"CDEF:power=kwh,3600000,*" \
		"XPORT:power:Puissance" > $GRAPH_PATH/$1.xml
}

create_composite_xml()
{
	echo Coalescing values into $1.json
	# Header

	echo '[' > $GRAPH_PATH/$1.json

	# Values
	# Day first
	echo '{ 
		"name": "'$2'",
		"data": [ ' >> $GRAPH_PATH/$1.json

	sed -n -e '/NaN/d' -e 's;.*<t>\(.*\)</t><v>\(.*\)</v>.*;\t[\1000, \2],;p' $GRAPH_PATH/$2.xml  >> $GRAPH_PATH/$1.json
	truncate -s -2 $GRAPH_PATH/$1.json
	echo ']}' >> $GRAPH_PATH/$1.json

	# Week as a separate series
	echo ', { 
		"name": "'$3'",
		"data": [ ' >> $GRAPH_PATH/$1.json

	sed -n -e '/NaN/d' -e 's;.*<t>\(.*\)</t><v>\(.*\)</v>.*;\t[\1000, \2],;p' $GRAPH_PATH/$3.xml  >> $GRAPH_PATH/$1.json
	truncate -s -2 $GRAPH_PATH/$1.json

	echo ']}' >> $GRAPH_PATH/$1.json

	if [ -n "$4" ]; then
		# Year as a separate series
		echo ', { 
			"name": "'$4'",
			"data": [ ' >> $GRAPH_PATH/$1.json

		sed -n -e '/NaN/d' -e 's;.*<t>\(.*\)</t><v>\(.*\)</v>.*;\t[\1000, \2],;p' $GRAPH_PATH/$4.xml  >> $GRAPH_PATH/$1.json
		truncate -s -2 $GRAPH_PATH/$1.json
		echo ']}' >> $GRAPH_PATH/$1.json
	fi


	# Close	
	echo ']' >> $GRAPH_PATH/$1.json

}

if [ "$1" != "--xml" ]; then
	rm -f $GRAPH_PATH/temperature*.png
	rm -f $GRAPH_PATH/edf*.png
	rm -f $GRAPH_PATH/gas*.png
	graph_temperature temperature_2hour -2h
	graph_temperature temperature_day -1d
	graph_temperature temperature_week -1w
	graph_temperature temperature_month -1m
	graph_temperature temperature_year -1y

	graph_edf edf_2hour -2h
	graph_edf edf_day -1d
	graph_edf edf_week -1w
	graph_edf edf_month -1m
	graph_edf edf_year -1y
	graph_gas gas_2hour -2h
	graph_gas gas_day -1d
	graph_gas gas_week -1w
	graph_gas gas_month -1m
	graph_gas gas_year -1y
else 
	export_temperature temperature_5min -300d now 100000
	export_temperature temperature_day -369d -1d 
	for where in officeAH pantry exterior living bed; do
		create_composite_xml temperature_$where temperature_5min_$where temperature_day_$where
	done
	export_edf edf_1min -2w now 10000
	export_edf edf_1hour -30w now 10000
	export_edf edf_day -2y now 1000
	create_composite_xml edf edf_1min edf_1hour edf_day
	export_gas gas_1min -2w now
	export_gas gas_1hour -30w now
	export_gas gas_1day -2y now 1000
	create_composite_xml gas gas_1min gas_1hour gas_1day
fi
