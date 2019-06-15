#include <stdio.h>
#include <string.h>
#include <stdlib.h>

#define STREQ(buf, s) !strncmp(buf, s, strlen(s))

static void teleinfo_line(const char *cmd) 
{
	if (STREQ(cmd, "ADCO ") ||
		STREQ(cmd, "OPTARIF ") ||
		STREQ(cmd, "ISOUSC ") ||
		STREQ(cmd, "PTEC ") ||
		STREQ(cmd, "IMAX ") ||
		STREQ(cmd, "MOTDETAT ")) {
		// Ignore these, they are not interesting
		return;
	}

	// In fact, the only interesting ones are ADPS, IINST, PAPP, and BASE

	// Avertissement de Dépassement de Puissance Souscrite
	if (STREQ(cmd, "ADPS ")) {
		// XXX NOT TESTED YET warn everyone to turn things off because the breaker is going to blow
		system("cd ../power_warning; ./warn_power.sh ''");
		system("echo 'ADPS warning ' | mail root");
	} else if (STREQ(cmd, "PAPP")) {
		// Accumulate PAPP over one minute then report to web server
	} else if (STREQ(cmd, "BASE")) {

	}

//"localhost:5000/update/electricity/%f,%d
	printf("tele %s\n", cmd);	
}

void handle_serial_input_line(const char *cmd) 
{
	if (STREQ(cmd, "TELE ")) {
		// Teleinfo command
		teleinfo_line(cmd + 5);
	} else {
		printf("XXXfromserial \"%s\"\n", cmd);
	}
}
