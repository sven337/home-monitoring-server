#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdarg.h>
#include <string.h>
#include "mqtt_login.h"

#define PIPE_LINKY_ID 3
#define PIPE_THERMOMETER_ID 4

static void mqtt_report(const char *prefix, const char *topic, const char *fmt, ...)
{
	va_list ap;
	va_start(ap, fmt);

	char message[256];
	vsnprintf(message, 255, fmt, ap);

	char command[2048];
	sprintf(command,  "mosquitto_pub -h 192.168.1.6 -t '%s/%s' -u %s -P %s  -i rf24_updater -m '%s'", prefix, topic, MQTT_USER, MQTT_PASS, message);
	system(command);
	va_end(ap);
}

static int therm_message(uint8_t *p)
{
#undef UNK
#define UNK  printf("Unknown thermometer message %c %c %c %c\n", p[0], p[1], p[2], p[3]); return 1;
	char buf[1000];
	uint16_t value;
	int16_t temperature;
	int temperature_error = 0;
	float volt, level;
	const char *location = "";

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
			volt = value*3.3f/1024; //no voltage divider so no 2*
			level = (volt-0.8)/(1.5-0.8); //boost cutoff at 0.8
			printf("Thermometer %s battery level: %.2fV = %f%% n", location, volt, 100*level);
			sprintf(buf, "mosquitto_pub -h 192.168.1.6 -t '%s_thermometer/battery' -u %s -P %s  -i rf24_updater -m '%d'", location, MQTT_USER, MQTT_PASS, (int)(100*level));
			system(buf);
			break;
		case 'T':
			temperature = p[2] << 8 | p[3];
			if (temperature == (int16_t)0xFFFF) {
				temperature_error = 1;
			}
			printf("Thermometer %s temperature: %.1f°C\n", location, temperature/16.0f);
			if (!temperature_error) {
				sprintf(buf, "mosquitto_pub -h 192.168.1.6 -t '%s_thermometer/temperature' -u %s -P %s -r -i rf24_updater -m '%.1f'", location, MQTT_USER, MQTT_PASS, temperature/16.0f);
				system(buf);
			}
			break;
		case 'F':
			printf("Thermometer %s reports no ACK received when sending temperature\n", location);
			sprintf(buf, "date");
			system(buf);
			break;
		default:
			UNK;
	}
	return 0;
}

static int linky_message(uint8_t *p)
{
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
	};

	for (unsigned int i = 0; i < sizeof(mapping)/sizeof(mapping[0]); i++) {
		if (!mapping[i].frame_type) {
			continue;
		}
		if (mapping[i].frame_type != p[0]) {
			continue;
		}

		// Found mapping, reconstitute data (if applicable) and report
		const char *name = mapping[i].name;
		char data[16] = { 0 };

		// no special treatment for PTEC, DEMAIN, IINST, ADPS
		memcpy(data, &p[1], 3);
		if (!strcmp(name, "PAPP")) {
			// Only 3 characters, add a zero at the end to reconstitute VA
			data[3] = '0';
		}

		if (!strncmp(name, "BBRH", 4)) {
			uint32_t val = p[1] << 16 | p[2] << 8 | p[3];
			val <<= 6;
			sprintf(data, "%d", val);
		}
		printf("linky: %s = %s\n", name, data);
		mqtt_report("edf", name, "%s", data); 
		
		return 0;
	}

	return 1;
}


int handle_rf24_cmd(uint8_t pipe_id, uint8_t data[4]) 
{
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
