#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include <time.h>
#include <ctype.h>
#include <unistd.h>
#include <mosquitto.h>
#include "mqtt_login.h"

#define PIPE_LINKY_ID 3
#define PIPE_THERMOMETER_ID 4
#define MQTT_HOST "192.168.1.6"
#define MQTT_PORT 1883
#define MQTT_KEEPALIVE 60

// Global MQTT client
static struct mosquitto *mosq = NULL;
static bool mqtt_connected = false;

unsigned int gas_pulse_counter = 0;
unsigned int water_pulse_counter = 0;

static uint32_t prev_bbrh_values[6] = {0}; // Store previous values for sanity-checking

static void on_mqtt_connect(struct mosquitto *mosq, void *userdata, int result)
{
	if (result == 0) {
		mqtt_connected = true;
		printf("MQTT: Connected to broker\n");
	} else {
		mqtt_connected = false;
		printf("MQTT: Connection failed with code %d\n", result);
	}
}

// MQTT disconnection callback
static void on_mqtt_disconnect(struct mosquitto *mosq, void *userdata, int result)
{
	mqtt_connected = false;
	printf("MQTT: Disconnected from broker\n");
}

// Initialize MQTT client
static int mqtt_init(void)
{
	int rc;
	
	// Initialize library
	mosquitto_lib_init();
	
	// Create client instance
	mosq = mosquitto_new("rf24_updater", true, NULL);
	if (!mosq) {
		printf("MQTT: Failed to create mosquitto instance\n");
		return -1;
	}

	mosquitto_int_option(mosq, MOSQ_OPT_PROTOCOL_VERSION, MQTT_PROTOCOL_V5);

	// Set callbacks
	mosquitto_connect_callback_set(mosq, on_mqtt_connect);
	mosquitto_disconnect_callback_set(mosq, on_mqtt_disconnect);
	
	// Set username and password
	rc = mosquitto_username_pw_set(mosq, MQTT_USER, MQTT_PASS);
	if (rc != MOSQ_ERR_SUCCESS) goto err;
	
	// Connect to broker
	rc = mosquitto_connect(mosq, MQTT_HOST, MQTT_PORT, MQTT_KEEPALIVE);
	if (rc != MOSQ_ERR_SUCCESS) goto err;
	
	// Start the network loop
	rc = mosquitto_loop_start(mosq);
	if (rc != MOSQ_ERR_SUCCESS) goto err;
	
	// Wait a bit for connection to establish
	usleep(100000); // 100ms
	
	return 0;
err:
	printf("MQTT: Failed to initialize: %s\n", mosquitto_strerror(rc));
	mosquitto_destroy(mosq);
	mosquitto_lib_cleanup();
	return -1;
}

static void mqtt_publish(const char *topic, const char *message)
{
	int retry = 1;
	do {
		int rc = mosquitto_publish(mosq, NULL, topic, strlen(message), message, 0, false);
		if (rc == MOSQ_ERR_SUCCESS) {
			break;
		}
		if (rc == MOSQ_ERR_NO_CONN) {
			printf("MQTT: Not connected, attempting to reconnect before publishing to %s\n", topic);
			mosquitto_reconnect(mosq);
			usleep(100000); // 100ms
		}
	} while (retry--);
}

static void mqtt_publish_fmt(const char *topic, const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);

	char message[256];
	vsnprintf(message, 255, fmt, ap);

	mqtt_publish(topic, message);
	
	va_end(ap);
}

static int therm_message(uint8_t *p)
{
#undef UNK
#define UNK  printf("Unknown thermometer message %c %c %c %c\n", p[0], p[1], p[2], p[3]); return 1;
	uint16_t value;
	int16_t temperature;
	int temperature_error = 0;
	float volt, level;
	const char *location = "";
    uint8_t dual_cell = 0;

	switch (p[1]) {
		case 'E':
			location = "exterior";
			break;
		case 'K':
			location = "kidbed";
			break;
		case 'L':
			location = "jh";
			break;
		case 'P':
			location = "pool";
            dual_cell = 1;
			break;
		case 'B':
			location = "bed";
			break;
		case 'R':
			location = "rochelle";
			break;
		default:
			UNK;
	}

	switch (p[0]) {
		case 'B':
			value = p[2] << 8 | p[3];
			volt = value*3.3f/1024;
			/* Single cell */
			level = (volt-0.8)/(1.5-0.8); //boost cutoff at 0.8
            if (dual_cell) {
                /* 2S: warn at 0.9V/cell = 1.8V to limit deep discharge */
                level = (volt-1.8)/(2.75-1.8);
            }

			printf("Thermometer %s battery level: %.2fV = %f%%\n", location, volt, 100*level);
			
			char topic[256];
			snprintf(topic, 255, "%s_thermometer/battery", location);
			mqtt_publish_fmt(topic, "%d", (int)(100*level));
			break;
		case 'T':
			temperature = p[2] << 8 | p[3];
			if (temperature == (int16_t)0xFFFF) {
				temperature_error = 1;
			}
			printf("Thermometer %s temperature: %.1f�C\n", location, temperature/16.0f);
			if (!temperature_error) {
				char topic[256];
				snprintf(topic, 255, "%s_thermometer/temperature", location);
				mqtt_publish_fmt(topic, "%.1f", temperature/16.0f);
			}
			break;
		case 'F':
			printf("Thermometer %s reports no ACK received when sending temperature\n", location);
			system("date");
			break;
		default:
			UNK;
	}
	return 0;
}

static int linky_message(uint8_t *p)
{
	static int last_PAPP;

	struct {
		const char *name;
		uint8_t frame_type;
	} mapping[] = {
			{ "BBRHCJB", 'b'}, //033487837 H
			{ "BBRHPJB", 'B'}, //006345478 O
			{ "BBRHCJW", 'w'}, //000000000 2
			{ "BBRHPJW", 'W'}, //000000000 ?
			{ "BBRHCJR", 'r'},  //000000000 -
			{ "BBRHPJR", 'R'}, //000000000 :
			{ "PAPP",    'P'}, //00000 !
			{ "PTEC",    'J'}, //HPJB P
			{ "DEMAIN",  'D'}, //---- "
			{ "IINST",   'I'}, //003 Z
			{ "ADPS",    'A'},
			{ "GAS",     'G'},
			{ "WATER",   'E'},
	};

	for (unsigned int i = 0; i < sizeof(mapping)/sizeof(mapping[0]); i++) {
		if (mapping[i].frame_type != p[0]) {
			continue;
		}

		// Found mapping, reconstitute data (if applicable) and report
		const char *name = mapping[i].name;
		char data[16] = { 0 };

		// No special treatment for PTEC, DEMAIN, IINST, ADPS
		memcpy(data, &p[1], 3);

		// Sanity check for PAPP
		if (!strcmp(name, "PAPP")) {
			for (int j = 0; j < 3; j++) {
				if (!isdigit(p[j+1])) {
					printf("Error: Non-digit character in %s value. Received value: %02X %02X %02X\n", 
						   name, p[1], p[2], p[3]);
					return 1;
				}
			}
		}

		if (!strcmp(name, "PAPP")) {
			// Only 3 characters, add a zero at the end to reconstitute VA
			data[3] = '0';
			last_PAPP = atoi(data);
		}

		if (!strncmp(name, "BBRH", 4)) {
			uint32_t val = p[1] << 16 | p[2] << 8 | p[3];
			val <<= 6;
			sprintf(data, "%d", val);

			// Check difference with previous value
			char *brrh_frame_type = strchr("bBwWrR", p[0]);
			if (brrh_frame_type == NULL) {
				printf("Error: Invalid BBRH frame type '%c' (0x%02X)\n", p[0], p[0]);
				return 1;
			}
			int bbrh_index = brrh_frame_type - "bBwWrR";
			if (prev_bbrh_values[bbrh_index] != 0) {
				int32_t diff = abs((int32_t)val - (int32_t)prev_bbrh_values[bbrh_index]);
				if (diff > 4096) {
					printf("Error: %s value differs from previous by more than 4096.\n"
						   "Received value: %d, Previous value: %d. Seems bogus, ignoring.\n", 
						   name, val, prev_bbrh_values[bbrh_index]);
					return 1;
				}
			}
			prev_bbrh_values[bbrh_index] = val;
		}

		if (!strcmp(name, "ADPS")) {
			// warn everyone to turn things off because the breaker is going to blow
			// No beep between 10PM and 8AM
			time_t t = time(NULL);
			struct tm *tm = localtime(&t);
			char hour_of_day_str[10];
			unsigned int hour_of_day;
			strftime(hour_of_day_str, 10, "%H", tm);
			hour_of_day = atoi(hour_of_day_str);

			// Threshold min 7300VA to warn: on a 6kVA subscription the Linky will allow 1.3x = 7800VA indefinitely
			if (last_PAPP > 7300 && hour_of_day >= 8 && hour_of_day < 22) {
				system("cd ../power_warning; ./warn_power.sh ''");
			}

			strcpy(data, "1"); // better looking than 30 (amps subscription)
		}

		if (!strcmp(name, "GAS")) {
			gas_pulse_counter++;
			// Each pulse is 10 liters, and 11.05kWh/m3
			sprintf(data, "%.2f", gas_pulse_counter * 10.0 * 11.05 / 1000.0);
		} 
		
		if (!strcmp(name, "WATER")) {
			water_pulse_counter++;
			sprintf(data, "%d", water_pulse_counter);
		}

		printf("linky: %s = %s\n", name, data);
		
		char topic[256];
		snprintf(topic, 255, "edf/%s", name);
		mqtt_publish_fmt(topic, "%s", data); 
		
		return 0;
	}

	return 1;
}


int handle_rf24_cmd(uint8_t pipe_id, uint8_t data[4]) 
{
	if (!mosq) {
		if (mqtt_init()) {
			return 1;
		}
	}

	int error = 0;
	switch (pipe_id) {
		case PIPE_THERMOMETER_ID:
			return therm_message(data);
		case PIPE_LINKY_ID:
			return linky_message(data);
		default:
			error = 1;
			fprintf(stderr, "Received message on unknown pipe id %d: %c %c %c %c\n", pipe_id, data[0], data[1], data[2], data[3]);
	}

	return error;
}
