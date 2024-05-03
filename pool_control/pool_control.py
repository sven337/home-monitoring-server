#!/usr/bin/python

import ssl
import paho.mqtt.client as mqtt

import time
import datetime
import mqtt_creds

# MQTT var tracking when it was last seen and default value. Takes a timeout in seconds
class mqtt_var:

    def __init__(self, name, default_value, timeout=300):
        self.__name = name
        self.__last_seen = 0
        self.__value = default_value
        self.__default_value = default_value
        self.__timeout = timeout

    def get(self):
        if time.time() > self.__last_seen + self.__timeout:
            # Invalid value
            return self.__default_value
        return self.__value

    def set(self, value):
        self.__last_seen = time.time()
        if value != self.__value:
            print("Got " + self.__name + " " + str(value))
        self.__value = value


        

# PAPP "apparent power". 0 when injecting
house_apparent_power = mqtt_var("PAPP", -1)
house_net_power = mqtt_var("net power", -1)
# solar production
solar_power = mqtt_var("solar prod", -1, timeout=60)
pool_temperature = mqtt_var("pool temperature", -1, timeout=3600)
exterior_temperature = mqtt_var("exterior temperature", 10, timeout=3600)

last_msg = ""

def cb_ADPS(client, userdata, msg):
    # ADPS: stop pumping for 30 minutes
    injection_tracker.notify_ADPS()

def cb_PAPP(client, userdata, msg):
    house_apparent_power.set(int(msg.payload))
    
def cb_PTEC(client, userdata, msg):
    PTEC = msg.payload.decode('ascii')
    injection_tracker.notify_PTEC(PTEC)

def cb_PVprod(client, userdata, msg):
    solar_power.set(float(msg.payload))

class PoolTimeTracker:
    def __init__(self):
        self.target_filtration_hours = 2
        self.elapsed_filtration_hours = 0
        self.next_reset_counters_at = 0
        self.pump_status = None
        self.pump_started_at = None
        self.last_set_pump_at = 0
        self.filter_more_today = 0
        self.night_start_at = 0
        self.check_day_change()

    # Check if new day -> reset counters
    def check_day_change(self):
        # Reset counters every day at 6
        if time.time() > self.next_reset_counters_at:
            self.next_reset_counters_at = datetime.datetime.combine(datetime.date.today() + datetime.timedelta(days=1), datetime.time(6,0)).timestamp()
            self.elapsed_filtration_hours = 0
            self.filter_more_today = 0
            self.night_start_at = 0

    # Get run time for the current cycle
    def get_pump_current_cycle_run_time(self):
        if not self.pump_started_at or not self.pump_status:
            return 0
        return (time.time() - self.pump_started_at) / 3600.0
       
    def get_pump_total_run_time(self):
        return self.elapsed_filtration_hours + self.get_pump_current_cycle_run_time()
    
    def remaining_pump_hours(self):
        return self.target_filtration_hours - self.get_pump_total_run_time()

    # Relay state has changed     
    def notify_relay_state(self, state):
        self.check_day_change()
        if state == self.pump_status:
            # Nothing changed? bail
            return
        if state == 1:
            # Pump just turned on, start counting
            self.pump_started_at = time.time()
        else:
            # Pump just turned off, stop counting
            self.elapsed_filtration_hours += self.get_pump_current_cycle_run_time()
        # Change pump_status after updating the accounting, not before!
        self.pump_status = state
  
    def update_target_filtration_hours(self):
        self.check_day_change()
        old_target = self.target_filtration_hours

        # Calculate filtration time based on pool temperature...
        t = pool_temperature.get() 
        if t < 15: # includes case -1 = invalid value
            self.target_filtration_hours = 2
        elif t < 20:
            # 4h + 0.5h/degree above 15, so 16 is 4.5h and 20 is 6.5h
            self.target_filtration_hours = 4 + (t - 15) / 2
        elif t < 25:
            # 7h + 1h/degree above 20, so 21 is 8h and 25 is 12h
            self.target_filtration_hours = 7 + (t - 20)
        elif t >= 25:
            # Super hot? temperature/2
            self.target_filtration_hours = t / 2


        # Modulate according to exterior temp
        e = exterior_temperature.get()
        if e and e > 25:
            # If it's hot, filter more
            self.target_filtration_hours += 2
        if e and e < 15:
            # If it's cold, filter less
            self.target_filtration_hours -= 1

        # Always ensure a daily minimum of 2h of runtime...
        if self.target_filtration_hours < 2:
            self.target_filtration_hours = 2

        # ... except for the manual override
        self.target_filtration_hours += self.filter_more_today

        if self.target_filtration_hours < 0:
            self.target_filtration_hours = 0

        if old_target != self.target_filtration_hours:
            log("Changing target filtration hours from %.1f to %.1f" % (old_target, self.target_filtration_hours))
        
    
    # At night, there is no solar production, but filtration may need to run:
    #   - in winter to prevent icing (3-5AM)
    #   - rest of the time if not enough filtration happened during the day
    def night_cycle_tick(self):
        hour = datetime.datetime.now().hour
        night = hour > 21 or hour < 6

        # Not at night? do nothing and let the rest run
        if not night:
            return False
    
        # Allow pumping between 2 and 5
        if hour < 2 or hour > 5:
            # ... if outside of this time, stop the pump, and eat the event
            self.set_pump(0)
            return True

        r = self.remaining_pump_hours()

        # Ran long enough during the day already?
        if r <= 0:
            self.set_pump(0)
            return True

        # If the pump is not running, decide when to start it,  so that it stops at 5AM
        if self.night_start_at == 0:
            start_offset = r * 3600
            stop_time = datetime.datetime.combine(datetime.date.today(), datetime.time(5, 0)).timestamp()
            self.night_start_at = stop_time - start_offset

        if time.time() > self.night_start_at:
            self.set_pump(1)

        return True
           


    # Change the pump status. Block changes more often than every N minutes
    def set_pump(self, pump_state, force = False):
        self.check_day_change()
        # Implement hysteresis (for testing: 60s, production should be higher)
        if not force and time.time() - self.last_set_pump_at < 60:
            return
        
        # Eat duplicate events - makes caller logic easier
        if self.pump_status == pump_state:
            return

        self.last_set_pump_at = time.time()

        if pump_state == 0:
            pump_state = "OFF"
        elif pump_state == 1:
            pump_state = "ON"

        log("Changing relay to " + pump_state)
        mqtt.publish('zigbee2mqtt/smartrelay_piscine/set', pump_state)
        mqtt_publish_status()

            
    def __str__(self):
        s = '''Target filtration time: %.1fh\nElapsed filtration time: %.1fh\n''' % (self.target_filtration_hours, self.get_pump_total_run_time())
        s += '''Reset counters on ''' + str(datetime.datetime.fromtimestamp(self.next_reset_counters_at)) 
        s += '''\nPump is ''' + ("ON" if self.pump_status else "OFF")
        return s


            



class InjectionTracker:
    def __init__(self):
        self.power_state = 1 # 1 for consumption, -1 for injection
        self.power_state_since = 0 # time at which state changed last
        self.stopped_until = 0
        self.electricity_is_expensive = False
        self.net_power_ema = 1000
        self.last_net_power_at = 0
        self.energy_free_pump = 0
        self.energy_cost_pump = 0
        self.energy_oppmissed_pump = 0

    def __str__(self):
        s = ""
        if time.time() < self.stopped_until:
            s += 'ADPS until %s\n' % str(datetime.datetime.fromtimestamp(self.stopped_until))
        if self.power_state == 1:
            s += "Consuming "
        elif self.power_state == -1:
            s += "Injecting "
        s += "since %s\n" % str(datetime.datetime.fromtimestamp(self.power_state_since))
        s += "Net power (EMAd) %.0f\n" % self.net_power_ema
        return s
    
    def notify_PTEC(self, PTEC):
        if PTEC == "PJR":
            # HP JR = do not filter!!!
            # stop until 22h
            self.electricity_is_expensive = True
            self.stopped_until = datetime.datetime.combine(datetime.date.today(), datetime.time(22, 0)).timestamp()
            return
        elif PTEC == "PJW":
            # HP JW = increase threshold to decide to filter
            self.electricity_is_expensive = True
            return
        
        # Other cases proceed as normal. (PJB, CJB, CJR, HJW)
        self.electricity_is_expensive = False
           
    def notify_ADPS(self):
        # ADPS: cut everything for 30 minutes
        self.stopped_until = time.time() + 30 * 60

    def track_energy_cost(self, pump_status, power, duration):
        if pump_status:
            if power <= 0:
                # Pump is running and still injecting: we are using 1000W of free energy
                self.energy_free_pump += (1000 * duration) / 3600 
            else:
                # Pump is running and consuming: we are paying for min(power, 1000) since more than 1000 is other things than the pump
                self.energy_cost_pump += (min(power, 1000) * duration) / 3600
        else:
            if power < 1000:
                # Pump is not running, but injecting enough to run it: lost opportunity to run
                self.energy_oppmissed_pump += (1000 * duration) / 3600
            


    def injecting_pump_start_decision(self, pwr):
        # XXX take into account current solar production regardless of injection

        # Solar production usefully ends at 18h
        remaining_solar_hours = (datetime.datetime.combine(datetime.date.today(), datetime.time(18,0)) - datetime.datetime.now()).total_seconds() / 3600

        if pwr < -1100:
            # start pump if injecting more than 1100W regardless of current runtime, simple case
            log("injecting more than 1100W: start pump (filtration is " + ("REQUIRED" if pool_time_tracker.remaining_pump_hours() > 0 else "OPTIONAL") + ")")
            pool_time_tracker.set_pump(1)
            #  XXX track total optional time
            return

        # What threshold to use to start the pump
        house_power_allow_pump_threshold = -100 
        if self.electricity_is_expensive:
            house_power_allow_pump_threshold = -900

        if pool_time_tracker.remaining_pump_hours() <= 0:
            # Pump has run long enough already
            return
        
        if pwr < -1000:
            # start pump if injecting more than 1000W and more hours are needed
            pool_time_tracker.set_pump(1)
            log("injecting more than 1000W: start pump (filtration is " + ("REQUIRED" if pool_time_tracker.remaining_pump_hours() > 0 else "OPTIONAL") + ")")
            #  XXX track total optional time
            return

        # At this point there isn't enough injected power to run the pump
        # It can run up to 3h at night if need be, so bail if remaining hours <= 3
        if pool_time_tracker.remaining_pump_hours() <= 3:
            return

        if pool_time_tracker.remaining_pump_hours() > remaining_solar_hours:
            log("not injecting enough, but pump still-required runtime exceeds 18h: start pump")
            pool_time_tracker.set_pump(1)
            return

        # At this point, there is enough solar production time to cover the pump run time, if solar production can be expected to increase
        # peak production is at 13h, so if past 13h, start the pump whenever injecting, otherwise hold off until 13h
        hour = datetime.datetime.now().hour
        if pwr < house_power_allow_pump_threshold and hour >= 13:
            log("not injecting enough, but peak production is over : start pump")
            pool_time_tracker.set_pump(1)
            return

    def consuming_pump_stop_decision(self, pwr):
        house_power_stop_pump_threshold = 500
        hour = datetime.datetime.now().hour
        # Force the pump to stay off for a certain duration when deciding to stop?
        stop_duration = 0

        if self.electricity_is_expensive:
            house_power_stop_pump_threshold = 300
            stop_duration = 30 * 60

        if hour > 11 and hour < 13:
            # Free up some power between 11 and 13 for cooking if not injecting
            house_power_stop_pump_threshold = 200
            stop_duration = 30 * 60

        # Ran long enough? stop aggressively (can run up to 3 hours at night if need be)
        if pool_time_tracker.remaining_pump_hours() <= 3:
            house_power_stop_pump_threshold = 100 #XXX will have no effect due to caller threshold at abs()> 200
            stop_duration = 30 * 60

        if pwr > house_power_stop_pump_threshold:
            pool_time_tracker.set_pump(0)
            log("consuming more than %d W: stop pump" % house_power_stop_pump_threshold)
            if stop_duration > 0:
                self.stopped_until = time.time() + stop_duration

    def notify_net_house_power(self, pwr):
        # Receive notification of net power

        # Ignore redundant notifications every 15 sec
        if time.time() - self.last_net_power_at < 15:
            return
        last_net_power_at = self.last_net_power_at
        self.last_net_power_at = time.time()

        # EMA the incoming power data to smooth it out
        self.net_power_ema *= 9
        self.net_power_ema += pwr
        self.net_power_ema /= 10

        # ADPS
        if time.time() < self.stopped_until:
            print("Pump is forced off for %d minutes" % ((self.stopped_until - time.time()) / 60))
            pool_time_tracker.set_pump(0, force = True)
            return
        
        # if at night, no injection tracking to do,
        #    let night_cycle_tick consume the event
        if pool_time_tracker.night_cycle_tick():
            return
        
        self.track_energy_cost(pool_time_tracker.pump_status, pwr, time.time() - last_net_power_at)

        if self.net_power_ema < -100:
            # Injection
            if self.power_state == 1:
                self.power_state = -1
                self.power_state_since = time.time()
            else:
                if pool_time_tracker.pump_status == 1:
                    #Nothing to do if pump is already on
                    return
                if time.time() - self.power_state_since > 60 * 10:
                    # Been injecting for 10 minutes?
                    self.injecting_pump_start_decision(self.net_power_ema)
        elif self.net_power_ema > 100:
            # are we consuming and used not to? track the start point
            if self.power_state == -1:
                self.power_state = 1
                self.power_state_since = time.time()
            else:
                # Been consuming for a while?
                if pool_time_tracker.pump_status == 0:
                    # Nothing to do if pump is already off
                    return
                if time.time() - self.power_state_since > 60 * 10:
                    self.consuming_pump_stop_decision(self.net_power_ema)
                
def cb_netpower(client, userdata, msg):
    p = float(msg.payload)
    house_net_power.set(p)
    injection_tracker.notify_net_house_power(p)
        
def cb_pooltemp(client, userdata, msg):
    pool_temperature.set(float(msg.payload))
    pool_time_tracker.update_target_filtration_hours()

def cb_exteriortemp(client, userdata, msg):
    exterior_temperature.set(float(msg.payload))
    pool_time_tracker.update_target_filtration_hours()

def cb_relaystate(client, userdata, msg):
    msg = msg.payload.decode('ascii')
    if msg == "ON":
        pool_time_tracker.notify_relay_state(1) 
    elif msg == "OFF":
        pool_time_tracker.notify_relay_state(0)
    else:
        print("unknown pool relay state " + msg)

def cb_filter_more_today(client, userdata, msg):
    msg = msg.payload.decode('ascii')
    timeadd = float(msg)
    pool_time_tracker.filter_more_today = timeadd
    pool_time_tracker.update_target_filtration_hours() 
    log("manual override of filter time %d"  % timeadd)
    mqtt_publish_status()

def status():
    return str(injection_tracker) + "\n" + str(pool_time_tracker) + \
           "\nPool temperature: %.1f\n Exterior temperature: %.1f\n%s\n" % (pool_temperature.get(), exterior_temperature.get(), last_msg)

def log(msg):
    global last_msg 
    last_msg = msg
    print(msg)
    mqtt.publish('pool_control/log', msg)

def mqtt_publish_status():
    global last_msg
    mqtt.publish("pool_control/available", "online", qos=1, retain=True);
    if last_msg != "": 
        mqtt.publish("pool_control/log", last_msg)
    last_msg = ""

    mqtt.publish("pool_control/power_direction", injection_tracker.power_state)
    mqtt.publish("pool_control/power_direction_for", "%d" % (time.time() - injection_tracker.power_state_since))
    mqtt.publish("pool_control/ADPS_for", "%d" % (injection_tracker.stopped_until - time.time()))
    mqtt.publish("pool_control/target_filtration_hours", "%.1f" % pool_time_tracker.target_filtration_hours);
    mqtt.publish("pool_control/elapsed_filtration_hours", "%.1f" %  pool_time_tracker.get_pump_total_run_time());
    mqtt.publish("pool_control/remaining_filtration_hours", "%.1f" %  pool_time_tracker.remaining_pump_hours());
    mqtt.publish("pool_control/pump_status", pool_time_tracker.pump_status);
    mqtt.publish("pool_control/net_power_EMAd", "%.0f" % injection_tracker.net_power_ema);
    mqtt.publish("pool_control/filter_more_today", pool_time_tracker.filter_more_today);
    mqtt.publish("pool_control/energy_free_pump", "%d" % injection_tracker.energy_free_pump);
    mqtt.publish("pool_control/energy_cost_pump", "%d" % injection_tracker.energy_cost_pump);
    mqtt.publish("pool_control/energy_oppmissed_pump", "%d" % injection_tracker.energy_oppmissed_pump);

injection_tracker = InjectionTracker()
pool_time_tracker = PoolTimeTracker()

subscriptions = { 
    'edf/ADPS' : cb_ADPS,
    'edf/PAPP' : cb_PAPP,
    'edf/PTEC' : cb_PTEC,
    'solar/ac/power' : cb_PVprod,
    'zigbee2mqtt/main_panel_powermonitor/power_ab' : cb_netpower,
    'pool_thermometer/temperature' : cb_pooltemp,
    'exterior_thermometer/temperature' : cb_exteriortemp,
    'zigbee2mqtt/smartrelay_piscine/state' : cb_relaystate,
    'pool_control/send_status' : lambda x,y,z: mqtt_publish_status(),
    'pool_control/filter_more_today/set' : cb_filter_more_today,
}

mqtt = mqtt.Client("pool_control")
mqtt.username_pw_set(**mqtt_creds.auth)

mqtt.will_set("pool_control/available", "offline", qos=1, retain=True)
mqtt.connect(mqtt_creds.hostname, 1883)
mqtt.loop_start()

# Subscribe to all var tracking topics
for k, v in subscriptions.items():
    mqtt.message_callback_add(k, v)
    mqtt.subscribe(k)

# Request relay status from Z2M
mqtt.publish('zigbee2mqtt/smartrelay_piscine/get/state', '')
# ...ideally, would do the same for temperatures but that is not available (RF24bridge would need to be updated)

def run_forever():
    send_next_ping_at = 0
    while True:
        # Send MQTT status periodically
        if time.time() > send_next_ping_at:
            send_next_ping_at = time.time() + 300
            mqtt_publish_status()

        time.sleep(1)
        

if __name__ == "__main__":
        run_forever()
