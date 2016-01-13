amixer sset PCM 255
amixer sset Master 100
amixer sset Speaker 100
mpg123 alarm.mp3 &
echo "POWER WARNING $1 W"| ~/sms-send-notification.sh
echo "POWER WARNING $1 W" | mail -s 'POWER WARNING'  root
