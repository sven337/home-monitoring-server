# home-monitoring-server
============

Home automation - collection of my "server side" tools.
Below is AI-generated description that is almost devoid of bullshit and generally accurate.


# Table of Contents
- [Swimming Pool Filtration Control System](#swimming-pool-filtration-control-system)
  - [Key Features](#key-features)
  - [System Components](#system-components)
    - [MQTT Variables](#mqtt-variables)
    - [PoolTimeTracker](#pooltimetracker)
    - [InjectionTracker](#injectiontracker)
  - [Key Functions](#key-functions)
    - [Filtration Time Calculation](#filtration-time-calculation)
    - [Pump Control Logic](#pump-control-logic)
    - [MQTT Integration](#mqtt-integration)
  - [Usage and Configuration](#usage-and-configuration)
  - [Home-assistant integration](#home-assistant-integration)
  - [Conclusion](#conclusion)
- [RF24Bridge](#rf24bridge)


# Swimming Pool Filtration Control System

This Python program implements an intelligent control system for swimming pool filtration, optimizing pump operation based on various factors such as power consumption, solar production, and temperature.

## Key Features

- Adaptive filtration time based on pool and exterior temperature
- Energy-efficient pump control utilizing solar production
- Night cycle management for completing required filtration
- Winter cycle protection against freezing
- Manual override capabilities
- MQTT integration for monitoring and control

## System Components

### MQTT Variables

The system uses MQTT variables to track various parameters:

- `house_apparent_power`: Apparent power consumption of the house
- `house_net_power`: Net power consumption (negative when injecting to grid)
- `solar_power`: Solar power production
- `pool_temperature`: Current pool water temperature
- `exterior_temperature`: Outdoor ambient temperature

### PoolTimeTracker

This class manages filtration time tracking and pump control:

- Calculates daily target filtration hours based on pool temperature
- Tracks elapsed filtration time
- Manages pump status and runtime
- Implements day change logic to reset counters

### InjectionTracker

This class optimizes pump operation based on power consumption and production:

- Tracks house power state (consuming or injecting)
- Manages pump start/stop decisions based on power thresholds
- Handles ADPS (power limit) notifications
- Tracks energy usage and savings

## Key Functions

### Filtration Time Calculation

The `update_target_filtration_hours()` method calculates the daily filtration time based on pool temperature:

- < 15°C: 2 hours
- 15-20°C: 4-6.5 hours (increases by 0.5h per degree)
- 20-25°C: 7-12 hours (increases by 1h per degree)
- ≥ 25°C: Half of the pool temperature in hours

Exterior temperature further modulates the filtration time:

- > 25°C: +1 hour
- < 15°C: -1 hour

### Pump Control Logic

The system decides when to run the pump based on several factors:

1. **Injection-based decisions**: Starts the pump when excess solar power is available
2. **Consumption-based decisions**: Stops the pump when house power consumption exceeds thresholds
3. **Night cycle**: Ensures minimum filtration is achieved, running between 2-5 AM if necessary
4. **Winter cycle**: Prevents freezing by forcing filtration when water temperature is below 10°C (November to April)

### MQTT Integration

The program uses MQTT for communication:

- Subscribes to topics for power, temperature, and relay state updates
- Publishes status updates, logs, and control commands
- Implements a will message for availability tracking

## Usage and Configuration

1. Set up MQTT credentials in `mqtt_creds.py`
2. Configure any specific thresholds or timings in the main script
3. Run the script to start the control system

The system can be monitored and controlled through MQTT topics:

- `pool_control/log`: Receives log messages
- `pool_control/filter_more_today/set`: Manually adjust filtration time
- `pool_control/disable_duration/set`: Temporarily disable the system

## Home-assistant integration
```
mqtt:
  sensor:
    - state_topic: "pool_control/target_filtration_hours"
      name: target_filtration_hours
      device_class: "duration"
      state_class: "measurement"
      device:
          identifiers: "pool_control"
          name: "pool_control"
      unique_id: "0xbabe_poolcontrol_target"
      unit_of_measurement: h
    
    - state_topic: "pool_control/elapsed_filtration_hours"
      name: elapsed_filtration_hours
      device_class: "duration"
      state_class: "measurement"
      device:
          identifiers: "pool_control"
          name: "pool_control"
      unique_id: "0xbabe_poolcontrol_elapsed"
      unit_of_measurement: h

    - state_topic: "pool_control/remaining_filtration_hours"
      name: remaining_filtration_hours
      device_class: "duration"
      state_class: "measurement"
      device:
          identifiers: "pool_control"
          name: "pool_control"
      unique_id: "0xbabe_poolcontrol_remaining"
      unit_of_measurement: h

    - state_topic: "pool_control/net_power_EMAd"
      name: net_power_EMAd
      state_class: "measurement"
      device:
          identifiers: "pool_control"
          name: "pool_control"
      unique_id: "0xbabe_poolcontrol_net_power_EMAd"
      unit_of_measurement: W
      device_class: "power"

    - state_topic: "pool_control/energy_free_required_pump"
      name: energy_free_required_pump
      state_class: "total_increasing"
      device:
          identifiers: "pool_control"
          name: "pool_control"
          manufacturer: "self"
      unique_id: "0xbabe_poolcontrol_energy_free_required_pump"
      unit_of_measurement: Wh
      device_class: "energy"
    
    - state_topic: "pool_control/energy_free_opportunistic_pump"
      name: energy_free_opportunistic_pump
      state_class: "total_increasing"
      device:
          identifiers: "pool_control"
          name: "pool_control"
          manufacturer: "self"
      unique_id: "0xbabe_poolcontrol_energy_free_opportunistic_pump"
      unit_of_measurement: Wh
      device_class: "energy" 

    - state_topic: "pool_control/energy_cost_pump"
      name: energy_cost_pump
      state_class: "total_increasing"
      device:
          identifiers: "pool_control"
          name: "pool_control"
      unique_id: "0xbabe_poolcontrol_energy_cost_pump"
      unit_of_measurement: Wh
      device_class: "energy"

    - state_topic: "pool_control/energy_oppmissed_pump"
      name: energy_oppmissed_pump
      state_class: "total_increasing"
      device:
          identifiers: "pool_control"
          name: "pool_control"
      unique_id: "0xbabe_poolcontrol_energy_oppmissed_pump"
      unit_of_measurement: Wh
      device_class: "energy"

    - state_topic: "pool_control/force_stop_for"
      name: energy_force_stop_for
      state_class: "measurement"
      device:
          identifiers: "pool_control"
          name: "pool_control"
      unique_id: "0xbabe_poolcontrol_force_stop_for"
      unit_of_measurement: min
      device_class: "duration"
  number:
    - command_topic: "pool_control/filter_more_today/set"
      state_topic: "pool_control/filter_more_today"
      name: filter_more_today
      device_class: "duration"
      device:
          identifiers: "pool_control"
          name: "pool_control"
      unique_id: "0xbabe_poolcontrol_filtermore"
      min: "-5"
      max: 5
      unit_of_measurement: h
    - command_topic: "pool_control/disable_duration/set"
      state_topic: "pool_control/disabled_for"
      name: disable_duration_
      device_class: "duration"
      device:
          identifiers: "pool_control"
          name: "pool_control"
      unique_id: "0xbabe_poolcontrol_disable_duration"
      min: "0"
      max: 720
      unit_of_measurement: min
```


## Conclusion

This swimming pool filtration control system provides an intelligent and energy-efficient solution for maintaining pool water quality while optimizing energy usage. It adapts to changing conditions and can be easily monitored and controlled remotely through MQTT.


I apologize for my mistake. You are correct, and I should not have assumed or stated that the data was formatted as JSON. Thank you for pointing this out. I also regret omitting the water and gas meters from my previous description. Let me provide a corrected and more accurate description of RF24Bridge's functionality:

# RF24Bridge

RF24Bridge creates a bridge between RF24 radio modules used for Linky teleinfo reading, thermometers, water meters, and gas meters, connecting them to a MQTT-based home automation system. Here's a description of its functionality:

1. Linky Teleinfo Reading:
   - Receives teleinfo data packets from RF24 nodes connected to Linky meters.
   - Processes these packets containing electricity consumption metrics.
   - Handles various Linky meter readings such as current power consumption and tariff information.

2. Thermometers:
   - Receives temperature data from RF24 nodes connected to thermometers.
   - Processes temperature packets, which include temperature readings and potentially battery status.
   - Supports different types of temperature sensors, including DS18B20 sensors.

3. Water Meters:
   - Receives data packets from RF24 nodes connected to water meters.
   - Processes water consumption data, likely including metrics such as current flow rate or total consumption.

4. Gas Meters:
   - Receives data packets from RF24 nodes connected to gas meters.
   - Processes gas consumption data, potentially including current usage or cumulative consumption.

Common features:
- Uses a packet structure that includes a node ID to distinguish between different sensors and meters.
- Implements error checking and validation of received data packets.
- Allows configuration of RF24 communication parameters such as channel and address settings through the command handler.
- Enables users to send commands to request data from specific nodes or configure RF24 nodes remotely.

The program bridges the RF24 radio communication with a serial interface, facilitating the integration of Linky meter data, temperature readings, water consumption, and gas usage from remote sensors into a MQTT-based home automation system. This allows for comprehensive monitoring of various home utilities and environmental conditions.


