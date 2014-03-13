#!/bin/bash

source rrd_config.rc

WIDTH="--width 700"
HEIGHT="--height 250"
LABEL="--vertical-label" 

graph_temperature()
{
	echo Rendering $1
	rrdtool graph $GRAPH_PATH/$1.png --width 800 --height 400 --vertical-label °C --start $2 \
			"DEF:temp=$RRD_PATH/temperature.rrd:TEMPERATURE:AVERAGE" \
			"VDEF:max=temp,MAXIMUM" \
			"VDEF:min=temp,MINIMUM" \
			"LINE2:temp#FF3F00:Température" \
			"HRULE:max#FF0000:Max" \
			"HRULE:min#0000FF:Min" \
			"GPRINT:max:Max %2.1lf °C" "GPRINT:max:le %d/%M/%y:strftime" \
			"GPRINT:min:Min %2.1lf °C" "GPRINT:min:le %d/%M/%y:strftime"
#			"VDEF:slope=temp,LSLSLOPE" "VDEF:inter=temp,LSLINT" \
#			"GPRINT:slope:Var %2.1lf %s°C/heure"
			
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
	rrdtool xport --maxrows $MAXROWS --start $2  --end $3\
			"DEF:temp=$RRD_PATH/temperature.rrd:TEMPERATURE:AVERAGE" \
			"VDEF:max=temp,MAXIMUM" \
			"VDEF:min=temp,MINIMUM" \
			"XPORT:temp:Temperature"\
			"PRINT:max:Max temp" \
			"PRINT:min:Min temp" > $GRAPH_PATH/$1.xml
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
		"DEF:kwh=$RRD_PATH/edf.rrd:ELEC_KWH:AVERAGE" \
		"CDEF:eurovect=kwh,0.1329,*" \
		"VDEF:euro=eurovect,TOTAL" \
		"VDEF:total=kwh,TOTAL" \
		"XPORT:power:Puissance"\
		"PRINT:euro:\"Prix total\""\
		"PRINT:total:kWh total\"" > $GRAPH_PATH/$1.xml
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
		"CDEF:eurovect=kwh,0.0576,*" \
		"VDEF:euro=eurovect,TOTAL" \
		"VDEF:total=kwh,TOTAL" \
		"VDEF:index=idx,LAST" \
		"XPORT:power:Puissance" > $GRAPH_PATH/$1.xml
}

create_composite_xml()
{
	echo Coalescing values into $1.xml
	# Header
	echo '<?xml version="1.0" encoding="ISO-8859-1"?>
<xport>' > $GRAPH_PATH/$1.xml
	egrep  '(meta|legend|entry)' $GRAPH_PATH/$1_day.xml >> $GRAPH_PATH/$1.xml
	echo '<data>' >> $GRAPH_PATH/$1.xml
	# Values
	for i in year week day; do
		egrep  '(<row>|<t>|<v>)' $GRAPH_PATH/$1_$i.xml  >> $GRAPH_PATH/$1.xml
	done
	echo '</data>
</xport>' >> $GRAPH_PATH/$1.xml

}

if [ "$1" != "--xml" ]; then
	rm -f $GRAPH_PATH/temperature*.png
	rm -f $GRAPH_PATH/edf*.png
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
	export_temperature temperature_day -1d now
	export_temperature temperature_week -1w -1d 
	export_temperature temperature_year -1y -1w 10000
	create_composite_xml temperature
	export_edf edf_day -1d now
	export_edf edf_week -1w -1d
	export_edf edf_year -1y -1w 10000
	create_composite_xml edf
	export_gas gas_day -1d now
	export_gas gas_week -1w -1d
	export_gas gas_year -1y -1w 10000
	create_composite_xml gas
fi
