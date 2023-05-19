#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>
#include "mqtt_login.h"

#define PIPE_LINKY_ID 3
#define PIPE_THERMOMETER_ID 4

static int therm_message(uint8_t *p)
{
#undef UNK
#define UNK  printf("Unknown thermometer message %c %c %c %c\n", p[0], p[1], p[2], p[3]); return 1;
	char buf[1000];
	uint16_t value;
	int16_t temperature;
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

int handle_rf24_cmd(uint8_t pipe_id, uint8_t data[4]) 
{
	int error = 0;
	switch (pipe_id) {
		case PIPE_THERMOMETER_ID:
			return therm_message(data);
			break;
		default:
			error = 1;
			fprintf(stderr, "Received message on unknown pipe id %d: %c %c %c %c\n", pipe_id, data[0], data[1], data[2], data[3]);
	}

	return error;
}
