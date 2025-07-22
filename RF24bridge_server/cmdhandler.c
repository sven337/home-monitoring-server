#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>
#include "mqtt_login.h"

extern int fd; // The serial fd from dterm.c
extern int handle_rf24_cmd(uint8_t pipe_id, uint8_t data[4]);

void rf24_send_message(uint8_t pipe_id, uint8_t data[4])
{
	fprintf(stderr, "Sending RF24 message to pipe %d: %x %x %x %x\n", pipe_id, data[0], data[1], data[2], data[3]);
	dprintf(fd, "p%hhu %hhx %hhx %hhx %hhx\n", pipe_id, data[0], data[1], data[2], data[3]);
}

static void rf24_line(const char *cmd)
{
	uint8_t data[4];
	uint8_t pipe_id;

	sscanf(cmd, "p%hhu %hhx %hhx %hhx %hhx", &pipe_id, &data[0], &data[1], &data[2], &data[3]); 

	if (handle_rf24_cmd(pipe_id, data)) {
		fprintf(stderr, "Did not understand RF24 cmd %s pipe %d data %x %x %x %x\n", cmd, pipe_id, data[0], data[1], data[2], data[3]);
	}
}

void handle_serial_input_line(const char *cmd) 
{
	if (!strncmp(cmd, "RF24 ", 5)) {
		rf24_line(cmd + 5);
	} else {
		printf("XXXfromserial \"%s\"\n", cmd);
	}
}
