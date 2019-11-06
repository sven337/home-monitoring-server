amixer sset PCM 255 > /dev/null
amixer sset Master 100 > /dev/null
amixer sset Speaker 100 > /dev/null
LAST_RUN_FILE=/tmp/.edf_adps_last_run_at
if [ -f $LAST_RUN_FILE ]; then
	if [ $(( ($(cat $LAST_RUN_FILE) + 10) < $(date +%s) )) -eq 0 ]; then
		echo time out
		exit 0
	fi
fi

date +%s > $LAST_RUN_FILE

mpg123 alarm.mp3 >/dev/null &
echo "POWER WARNING ADPS "| ~/sms-send-notification.sh
echo "POWER WARNING ADPS " | mail -s 'POWER WARNING'  root
