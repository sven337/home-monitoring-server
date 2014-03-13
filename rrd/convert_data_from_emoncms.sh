#!/bin/bash
source ~/.emoncms_api_key

#Temperature
curl -s "http://ABCDEF/emoncms/feed/data.json?id=2&start=&end=&dp=&apikey=$APIKEY" | sed 's/000,\"/:/g' | tr ',' '\n' | tr -d '[]"' | tac | ./rrd_update.sh temperature.rrd

#Elec
((curl -s "http://ABCDEF/emoncms/feed/data.json?id=2&start=&end=&dp=&apikey=$APIKEY" | sed 's/000,\"/:U:/g' | tr ',' '\n' | tr -d '[]"' | tac) ; (curl -s "http://ABCDEF/emoncms/feed/data.json?id=5&start=&end=&dp=&apikey=$APIKEY" | sed -e 's/000,\"/:/g' -e 's/,/:U,/g'| tr ',' '\n' | tr -d '[]"' | tac))  | ./merge_emoncms_feeds.py | egrep -v '^$' | egrep -v ':U$' 

#Gas
curl -s "http://ABCDEF/emoncms/feed/data.json?id=8&start=&end=&dp=&apikey=$APIKEY" | sed -e 's/000,\"/:/g' -e 's/,/:U,/g'| tr ',' '\n' | tr -d '[]"' | ./rrd_update.sh gas.rrd
curl -s "http://ABCDEF/emoncms/feed/data.json?id=11&start=&end=&dp=&apikey=$APIKEY" | sed -e 's/000,\"/:/g' -e 's/,/:U,/g'| tr ',' '\n' | tr -d '[]"' | ./rrd_update.sh gas.rrd
curl -s "http://ABCDEF/emoncms/feed/data.json?id=16&start=&end=&dp=&apikey=$APIKEY" | sed 's/000,\"/:U:/g' | tr ',' '\n' | tr -d '[]"' | tac | ./rrd_update.sh gas.rrd
