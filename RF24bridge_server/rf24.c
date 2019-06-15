#include <stdio.h>
#include <stdint.h>
#include <stdlib.h>

#define PIPE_GAZ_ID 1
#define PIPE_LEDLAMP_ID 2
#define PIPE_MAILBOX_ID 3
#define PIPE_THERMOMETER_ID 4

static int ledlamp_reply(uint8_t *p)
{
	char buf[1000];
	float temperature;
#undef UNK
#define UNK  printf("Unknown ledlamp reply %c %c %c %c\n", p[0], p[1], p[2], p[3]); return 1;
	switch (p[0]) {
		case 'T':
			// thermal event
			switch (p[1]) {
				case 'E':
					printf("Ledlamp thermal emergency, temp is %d\n", p[2] | p[3] << 8);
					break;
				case 'A':
					printf("Ledlamp thermal alarm, temp is %d\n", p[2] | p[3] << 8);
					break;
				case '0':
					printf("Ledlamp thermal stand down from alarm, temp is %d\n", p[2] | p[3] << 8);
					break;
				case 'N':
					printf("Ledlamp thermal notify: temp is %d\n", p[2] | p[3] << 8);
					break;
				default:
					UNK
			};
			break;
		case 'R':
			// remote command reply
			switch (p[1]) {
				case 'O':
					printf("Ledlamp remote reply: lamp is off\n");
					break;
				case '1':
					printf("Ledlamp remote reply: lamp is on, light level target %d\n", p[2] | p[3] << 8);
					break;
				default:
					UNK
			};
			break;
		case 'D':
			// light duty cycle event
			switch (p[1]) {
				case 'I':
					printf("Ledlamp increased power, duty cycle %d\n", p[2]);
					break;
				case 'D':
					printf("Ledlamp decreased power, duty cycle %d\n", p[2]);
					break;
				case 'N':
					printf("Ledlamp current duty cycle notify: %d\n", p[2]);
					break;
				default:
					UNK
			};
			break;
		case 'L':
			// light level event
			switch (p[1]) {
				case 'N':
					printf("Ledlamp current light level notify: %d\n", p[2]);
					break;
				default:
					UNK
			}
			break;
		case 'A':
			// ambiant event
			switch (p[1]) {
				case 'N':

					temperature = (p[2] << 8 | p[3]) / 100.0;
					printf("Ledlamp ambient temperature %f\n", temperature);
					sprintf(buf, "curl http://192.168.1.6:5000/update/temperature/officeAH/%f", temperature);
					system(buf);
					break;
				default:
					UNK
			}
			break;

		default:
			UNK
	}

	return 0;
}

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
		case 'N':
			location = "exterior";
			break;
		case 'K':
			location = "kidbed";
			break;
		case 'L':
			location = "living";
			break;
		default:
			UNK;
	}

	switch (p[0]) {
		case 'B':
			value = p[2] << 8 | p[3];
			volt = value*3.3f/1024; //no voltage divider so no 2*
			level = (volt-0.8)/(1.5-0.8); //boost cutoff at 0.8
			printf("Thermometer %s battery level: %fV = %f%% n", location, volt, 100*level);
			sprintf(buf, "curl http://192.168.1.6:5000/update/battery_level/%s_thermometer/%d", location, (int)(100*level));
			system(buf);
			break;
		case 'T':
			temperature = p[2] << 8 | p[3];
			printf("Thermometer %s temperature: %f°C\n", location, temperature/16.0f);
			sprintf(buf, "curl http://192.168.1.6:5000/update/temperature/%s/%f", location, temperature/16.0f);
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
		case PIPE_LEDLAMP_ID:
			return ledlamp_reply(data);
			break;
		case PIPE_THERMOMETER_ID:
			return therm_message(data);
			break;
		default:
			error = 1;
			fprintf(stderr, "Received message on unknown pipe id %d: %c %c %c %c\n", pipe_id, data[0], data[1], data[2], data[3]);
	}

	return error;
}
