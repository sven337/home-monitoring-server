#!/usr/bin/python
import paho.mqtt.client as mqtt
import os
import time

alarm_is_armed = False
alarm_triggered = False

door_status = {}

def send_notification(msg, mail=False, sms=False):
    if sms:
        os.system("echo '" + msg + "' | ~/sms-send-notification.sh");
    if mail:
        os.system("echo '" + msg + "' | mail -s 'Alarm notif' root")
    print(msg)

def alarm_armed():
    global alarm_is_armed
    # Check if any door is open ("alarm" status), in which case impossible to arm
    opened_rooms = [ r for r in door_status if door_status[r] == "alarm" ]
    if len(opened_rooms) > 0:
        send_notification("Cannot arm alarm, rooms open: " + str(opened_rooms), mail=True)
        arm_alarm(False)
        return
    send_notification("Alarm is armed", sms=True)
    alarm_is_armed = True

def alarm_disarmed():
    global alarm_is_armed
    global alarm_triggered
    send_notification("Alarm is disarmed", mail=True)
    alarm_is_armed = False
    alarm_triggered = False

def arm_alarm(arm):
    mqttc.publish("alarm/arm", payload="armed" if arm else "disarmed", qos=1, retain=True)

def trigger_alarm(room):
    global alarm_triggered
    mqttc.publish("alarm/arm", payload="triggered", qos=1, retain=True)
    send_notification("ALARM TRIGGERED ON ROOM " + room + " status is " + str(door_status), mail=True, sms=True)
    alarm_triggered = True

def process_autoarm_alarm():
# Arm the alarm if: 
#    - neither of my computers respond AND
#    - my mobile phone doesn't respond
# XXX use multiprocessing? especially for auto disarm

    hosts_to_ping = [ "192.168.1.2", "192.168.1.11", "192.168.1.17" ]
    for h in hosts_to_ping:
        ret = os.system("ping -c 1 -W 0.5 %s > /dev/null" % (h))
        if ret == 0:
            # One host pings: I am at home, do not arm alarm
            if alarm_is_armed:
                # This sucks because it will take time to react to alarm triggering (up to 3*ping timeout). Will do for now.
                arm_alarm(False)
            return 

    # No host responded: auto arm alarm
    if not alarm_is_armed:
        arm_alarm(True)


def on_connect(client, userdata, flags, rc):
   print("Connected With Result Code %s"% (str(rc)))

def on_disconnect(client, userdata, rc):
   print("Client Got Disconnected")

def on_message(client, userdata, message):
    room = message.topic.split('/')[-1]
    status = message.payload.decode()
    print("Message Recieved: " + room + " " + status)
    if room == "arm":
        if status == "armed":
            alarm_armed()
        elif status == "disarmed":
            alarm_disarmed()
#        elif status == "triggered":
            # do nothing
            
        return

    # Update door status
    door_status[room] = status
    if status == "alarm":
        if not alarm_triggered:
            if alarm_is_armed:
                trigger_alarm(room)
            elif room == "smoke" or room == "carbonmonox":
                trigger_alarm(room)



def on_subscribe(client, userdata, mid, granted_qos):
    print("on_subscribe %s %s %s %s" % (str(client), str(userdata), str(mid), str(granted_qos)))

def on_log(client, userdata, level, buf):
    return
    print("Log has %s" % (buf))

mqttc = mqtt.Client("alarmsrv")
mqttc.enable_logger()
mqttc.on_message = on_message
mqttc.on_connect = on_connect
mqttc.on_disconnect = on_disconnect
mqttc.on_subscribe = on_subscribe
mqttc.on_log = on_log
mqttc.connect("192.168.1.6", 1883)
mqttc.subscribe("alarm/#", qos=1)
mqttc.loop_forever()
