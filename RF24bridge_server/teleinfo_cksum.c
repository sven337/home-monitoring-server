#include <stdio.h>  
#include <stdlib.h>  
#include <string.h>  
#include <unistd.h>  
#include <stdint.h>

static int PAPP_accum;
static int BASE_accum;
static int PAPP_number;
static int BASE_number;

void accumulate_value(const char *label, const char *value)
{
	int val = atoi(value);
	if (!strcmp(label, "PAPP")) {
		PAPP_accum += val; 
		PAPP_number ++;
	} else if (!strcmp(label, "BASE")) {
		BASE_accum += val; 
		BASE_number ++;
	}

	if (PAPP_number == 60) {
//		fprintf(stderr, "appart.PAPP:%d\n", PAPP_accum/PAPP_number);
		printf("appart.PAPP:%d\n", PAPP_accum/PAPP_number);
		PAPP_accum = 0;
		PAPP_number = 0;
	}
	if (BASE_number == 60) {
//		fprintf(stderr, "appart.BASEKWH:%d\n", (BASE_accum/1000)/BASE_number);
		printf("appart.BASEKWH:%d\n", (BASE_accum/1000)/BASE_number);
		BASE_accum = 0;
		BASE_number = 0;
	}
}
/*          sum = 32
                for c in etiquette: sum = sum + ord(c)
                for c in valeur:        sum = sum + ord(c)
                sum = (sum & 63) + 32
                return chr(sum)
*/

static char compute_cksum(const char *label, const char *value)
{
	int sum = 32;
	int i;
	for (i = 0; i < strlen(label); i++) {
		sum += label[i];
	}
	for (i = 0; i < strlen(value); i++) {
		sum += value[i];
	}

	sum = (sum & 63) + 32;

	return sum;
}

void parse_message(char *msg)
{
	char *label = msg;
	char *value = strchr(label, ' ');
	char *cksum;
	if (!value) {
		fprintf(stderr, "Did not find value in message \"%s\"\n", msg);
		return;
	}
	*value = 0;
	value++;

	cksum = strchr(value, ' ');
	if (!cksum) {
		fprintf(stderr, "Did not find cksum in message \"%s\"\n", msg);
		return;
	}

	*cksum = 0;
	cksum++;

	if (*cksum != compute_cksum(label, value)) {
		fprintf(stderr, "%s %s has cksum %c, invalid on the wire.\n", label, value, *cksum);
		return;
	} else {
//		fprintf(stderr, "%s %s has valid cksum %c\n", label, value, *cksum);
		accumulate_value(label, value);
	}

}

