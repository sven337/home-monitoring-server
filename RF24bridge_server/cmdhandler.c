#include <stdio.h>
#include <string.h>
#include <stdlib.h>
#include <stdbool.h>
#include <stdint.h>
#include <inttypes.h>

extern int handle_rf24_cmd(uint8_t pipe_id, uint8_t data[4]);

static int teleinfo_last_index = 0;

// Accumulate PAPP over one minute then report to web server. Display it every minute too.
static int teleinfo_accumulate_PAPP(int papp)
{
	static int cnt = 0;
	static int accum = 0;

	accum += papp;
	cnt++;

	if (cnt == 60) {
		int val = accum / cnt;
		char buf[2048];
		sprintf(buf, "curl http://192.168.1.6:5000/update/electricity/%d,%d", val, teleinfo_last_index);
		system(buf);
		accum = 0;
		cnt = 0;
		return true; // print
	}

	if (!(cnt % 15)) {
		return true;
	}
	return false;
}

// Store the last value for teleinfo_accumulate_PAPP to report to web server. Display it every 5 minutes.
static int teleinfo_filter_BASE(int base) 
{
	static int cnt = 0;

	teleinfo_last_index = base / 1000;

	if (!cnt) {
		cnt++;
		return 1; // print
	}

	cnt = (cnt + 1) % 300;
	return 0;
}

static char teleinfo_cksum(const char *cmd)
{
	bool good;
	int sum = 32;
	int i;
	for (i = 0; i < strlen(cmd); i++) {
		if (cmd[i] == ' ') {
			break;
		}
		sum += cmd[i];
	}

	i++;
	for (; i < strlen(cmd); i++) {
		if (cmd[i] == ' ') {
			break;
		}
		sum += cmd[i];
	}

	sum = (sum & 63) + 32;
	
	char cksum = cmd[i+1];
	good = (cksum == sum);

	if (!good) {
		fprintf(stderr, "teleinfo cksum error on %s\n", cmd);
	}

	return good;
}

#define STREQ(buf, s) !strncmp(buf, s, strlen(s))
static void teleinfo_line(const char *cmd) 
{
	bool print = false;

	if (STREQ(cmd, "ADCO ") ||
		STREQ(cmd, "OPTARIF ") ||
		STREQ(cmd, "ISOUSC ") ||
		STREQ(cmd, "PTEC ") ||
		STREQ(cmd, "IMAX ") ||
		STREQ(cmd, "MOTDETAT ")) {
		// Ignore these, they are not interesting
		return;
	}

	if (!teleinfo_cksum(cmd)) {
		return;
	}

	// In fact, the only interesting ones are ADPS, PAPP, and BASE

	// Avertissement de Dépassement de Puissance Souscrite
	if (STREQ(cmd, "ADPS ")) {
		// XXX NOT TESTED YET warn everyone to turn things off because the breaker is going to blow
		system("cd ../power_warning; ./warn_power.sh ''");
		system("echo 'ADPS warning ' | mail root");
		print = true;
	} else if (STREQ(cmd, "PAPP ")) {
		int papp = atoi(cmd + 5);
		print = teleinfo_accumulate_PAPP(papp);
	} else if (STREQ(cmd, "BASE ")) {
		int base = atoi(cmd + 5);
		print = teleinfo_filter_BASE(base);
	}

	if (print) {
		printf("EDF %s\n", cmd);
	}
}

static void rf24_line(const char *cmd)
{
	uint8_t data[4];
	uint8_t pipe_id;

	// XXX this needs a pipe number too! can do without for now...
	sscanf(cmd, "p%hhu %hhx %hhx %hhx %hhx", &pipe_id, &data[0], &data[1], &data[2], &data[3]); 

	if (handle_rf24_cmd(pipe_id, data)) {
		fprintf(stderr, "Did not understand RF24 cmd pipe %d data %x %x %x %x\n", pipe_id, data[0], data[1], data[2], data[3]);
	}
}

void handle_serial_input_line(const char *cmd) 
{
	if (STREQ(cmd, "TELE ")) {
		// Teleinfo command
		teleinfo_line(cmd + 5);
	} else if (STREQ(cmd, "RF24 ")) {
		rf24_line(cmd + 5);
	} else {
		printf("XXXfromserial \"%s\"\n", cmd);
	}
}
