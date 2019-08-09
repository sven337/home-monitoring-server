#!/bin/bash
source rrd_config.rc

generate_temperature_json()
{
    RRD="$RRD_PATH/$1.rrd"
    JSON="$GRAPH_PATH/$1.json"
    F=$(mktemp)

	rrdtool dump $RRD > $F
    # Get entries into $F.{1 2 3}
    for i in 1 2 3; do
        xmlstarlet sel  -t  -c "//rrd//rra[cf=\"AVERAGE\"][${i}]/database" "$F" 2>/dev/null | grep -v 'NaN' | grep row | sed -e 's/.* \/ //' -e 's/ --.*<v>/, /' -e s'/<.*//'> ${F}.${i}
    done

    FIRSTDATE=$(head -n1 $F.2 | cut -f1 -d,)
    SECONDDATE=$(head -n1 $F.1 | cut -f1 -d,)

	echo FIRSTDATE is $FIRSTDATE SECONDDATE is $SECONDDATE
    echo '{ "name" : "'$1 '", "data": [' > $JSON
    cat $F.3 | awk "{ if (\$1 < $FIRSTDATE && \$1 < $SECONDDATE) { printf(\"[%s, %s],\n\", \$1 *1000, \$2) }}" >> $JSON
    FIRSTDATE=$(head -n1 $F.1 | cut -f1 -d,)
	echo FIRSTDATE is $FIRSTDATE
    cat $F.2 | awk "{ if (\$1 < $FIRSTDATE && \$1 < $SECONDDATE) { printf(\"[%s, %s],\n\", \$1 *1000, \$2) }}" >> $JSON
    cat $F.1 | awk "BEGIN { init_done = 0 } { if (!init_done) { init_done = 1; printf(\"[%s, %s]\n\", \$1 *1000, \$2)} else { printf(\",[%s, %s]\n\", \$1 *1000, \$2)} }" >> $JSON
    echo ']}' >> $JSON
    rm $F.[123] $F

}
for where in officeAH pantry exterior living bed kidbed; do
    generate_temperature_json temperature_$where
done
