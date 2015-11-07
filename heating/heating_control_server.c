#define _GNU_SOURCE
#include <stdlib.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <sys/select.h>
#include <unistd.h>
#include <string.h>
#include <unistd.h>
#include <errno.h>
#include <stdarg.h>
#include <time.h>

// Target temps in °C * 10
const int target_temp_cold = 175;
const int target_temp_away = 140;
const int target_temp_hot = 205;

// Stop heating when it's 16° outside
const int non_heating_exterior_temp = 160;

const int PORT = 45889;

const char *boiler_ip = "192.168.0.33";
const int boiler_port = 2222;

const char *temperature_srv_uri = "http://192.168.0.6:5000/last/temperature";

int sockfd; // UDP socket
struct sockaddr_in *clients[10];

time_t last_warning_at;
time_t next_status_dump_at;

enum state {
	HOT,
	COLD,
} current_state;

int current_burner_power = -1;
int is_away = 0;

int have_clients()
{
	return 1;
}

void send_to_clients(const char *buf, int len)
{
	unsigned int i;
	for (i = 0; i < sizeof(clients)/sizeof(clients[0]); i++) {
		if (clients[i]) {
			if (sendto(sockfd, buf, len, 0, (struct sockaddr *)clients[i], sizeof(struct sockaddr_in)) == -1) {
				perror("sendto");
				return;
			}
		}
	}
}


void hvprintf(const char *fmt, va_list args)
{
	char *str;
	vasprintf(&str, fmt, args);

	printf("%s", str);

	if (have_clients()) {
		send_to_clients(str, strlen(str));
	} else {
		// XXX what do we do here?
	}
	free(str);
}

// "Hub" printf
void hprintf(const char *fmt, ...) 
{
	va_list args;

	va_start(args, fmt);
	hvprintf(fmt, args);
	va_end(args);
}

int find_client(unsigned long addr)
{
	unsigned int i;
	for (i = 0; i < sizeof(clients)/sizeof(clients[0]); i++) {
		if (!clients[i]) {
			continue;
		} 

		if (clients[i]->sin_addr.s_addr == addr) {
			return i;
		}
	}

	return -1;
}

int add_client(struct sockaddr_in *si)
{
	unsigned int i;
	int index = find_client(si->sin_addr.s_addr);
	if (index != -1)
		// Client already registered, nothing to do
		return 1;

	for (i = 0; i < sizeof(clients)/sizeof(clients[0]); i++) {
		if (!clients[i]) {
			// Found a free slot
			clients[i] = (struct sockaddr_in *)calloc(1, sizeof(struct sockaddr_in));
			memcpy(clients[i], si, sizeof(struct sockaddr_in));
			return 0;
		}
	}
	return 0;
}

int create_socket(void)
{
	struct sockaddr_in si_me;

	sockfd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
	if (sockfd == -1) {
		perror("socket");
		exit(1);
	}

	memset(&si_me, 0, sizeof(si_me));
	si_me.sin_family = AF_INET;
	si_me.sin_port = htons(PORT);
	si_me.sin_addr.s_addr = htonl(INADDR_ANY);

	if (bind(sockfd, (struct sockaddr *)&si_me, sizeof(si_me)) == -1) {
		perror("bind");
		exit(1);
	}

	return 0;
}

static void hot(void)
{
	current_state = HOT;
}

static void cold(void)
{
	current_state = COLD;
}

static void away(void)
{
	is_away = 1;
}

static void back(void)
{
	is_away = 0;
}

static int get_temp(const char *name)
{
	char buf[2048];
	FILE *pipe;
	char value[150];
	float temperature;

	sprintf(buf, "curl -q %s/%s 2>/dev/null", temperature_srv_uri, name);
	pipe = popen(buf, "r");
	fgets(value, 149, pipe);
	if (!strcmp(value, "OLD")) {
		return -1;
	}
	temperature = strtof(value, NULL) * 10;
	pclose(pipe);

	printf("Returning temperature %d\n", (int)temperature);
	return (int)temperature;
}

static int get_interior_temp()
{
	return (get_temp("pantry") + 2 * get_temp("officeAH")) / 3;
}

static int get_exterior_temp()
{
	return get_temp("exterior");
}

static char *status_string(void)
{
	char *str;
	asprintf(&str, "State: %s. Burner power is %d. Ext temp %d, int temp %d\n", is_away ? "AWAY" : (current_state == HOT ? "HOT" : "COLD"), current_burner_power, get_exterior_temp(), get_interior_temp());
	return str;
}

static void status(void)
{
	char *str = status_string();
	hprintf(str);
	free(str);
}

static void set_burner_power(int power)
{
	// Send the new power order to the burner
	char buf[1024];
	const char *cmd;

	if (power == 0) {
		cmd = "OFF";
	} else if (power == 100) {
		cmd = "ON";
	} else {
		fprintf(stderr, "Invalid power %d received\n", power);
		return;
	}

	if (power != current_burner_power) {
		current_burner_power = power;
		sprintf(buf, "date; echo %s | nc -u -w 1 -q 1 boiler_ip %d", cmd, boiler_ip, boiler_port);
		system(buf);
	}
}

static void warn(const char *fmt, ...) 
{
	char buf[2048];
	sprintf(buf, "echo %s | mail -s 'Heater warning' root", fmt);

	if (time(NULL) - last_warning_at > 3600) {
		system(buf);
	}

	last_warning_at = time(NULL);
}

static void thermostat_loop(void)
{
	// température ext de non chauffage environ 15°C

    // dans un premier temps, fonctionnement en tout-ou-rien (avec température raisonnable configurée sur la chaudière) basé sur l'heure de la journée, température intérieure (corrigée), et température extérieure.

	int interior_temp = get_interior_temp();
	int exterior_temp = get_exterior_temp();
	int burner_power;
	int interior_temp_target = (current_state == HOT) ? target_temp_hot : target_temp_cold;
	
	if (interior_temp == -1 || exterior_temp == -1) {
		// interior or exterior temp is unreliable, warn and cut burner
		warn("Interior or exterior temperatures are -1.");
		burner_power = 0;
		goto out;
	}

	if (is_away && (interior_temp == -1  || interior_temp > target_temp_away)) {
		burner_power = 0;
		goto out;
	}

	if (exterior_temp >= non_heating_exterior_temp) {
		// If it's hotter outside than the non-heating temperature threshold, cut power completely
		burner_power = 0;
	} else {
		// XXX climatic control, for now just use 100
		burner_power = 100;
	}

	if (interior_temp < interior_temp_target - 5) {
		if (!burner_power) {
			warn("Exterior is at no-heat temperature, but internal temp is below target!");
		}
		burner_power = 100;
	} else if (interior_temp > interior_temp_target + 5) {
		if (burner_power == 100) {
			// XXX remove once we have climatic control
			warn("Exterior requests heating, but internal temp is above target!");
		}
		burner_power = 0;
	} else {
		// Temperature is within internal constraints - heat or not based on exterior decision
		;
	}

out:
	set_burner_power(burner_power);
}

static void handle_command(const char *buf)
{
	struct {
		const char *cmd;
		void (*fn)(void);
	} actions[] = 
		{
			{ "hot", hot },
			{ "cold", cold },
			{ "away", away },
			{ "back", back },
			{ "status", status },
		};

	for (unsigned int i = 0; i < sizeof(actions)/sizeof(actions[0]); i++) {
		if (!strncmp(buf, actions[i].cmd, strlen(actions[i].cmd))) {
			actions[i].fn();
			return;
		}
	}

	hprintf("Unknown command %s\n", buf);
}

void read_client_command(int fd, char *buf, int sz) 
{
	struct sockaddr_in si_from;
	int addr_len = sizeof(struct sockaddr_in);
	int len = 0;
	errno = 0;
	len = recvfrom(fd, buf, sz, 0, (struct sockaddr *)&si_from, (socklen_t *)&addr_len);

	if (len == -1) {
		perror("recvfrom");
		return;
	}
	buf[len] = 0;

	printf("Got client command %s\n", buf);
	if (si_from.sin_family != AF_INET) {
		// Localhost comes from netlink and not UDP, why the hell?!
		return;
	}

	add_client(&si_from);

	handle_command(buf);
}

void loop(void)
{
	char cmdbuf[4096];
	fd_set rfd;
	struct timeval tv;
	int ret;

	FD_ZERO(&rfd);
	FD_SET(sockfd, &rfd);

	tv.tv_sec = 15;
	tv.tv_usec = 0;

	ret = select(sockfd+1, &rfd, NULL, NULL, &tv);

	if (ret) {
		read_client_command(sockfd, cmdbuf, sizeof(cmdbuf));
		cmdbuf[0] = 0;
	}

	thermostat_loop();

	if (time(NULL) > next_status_dump_at) {
		char *str = status_string();
		char timestr[50];
		time_t t = time(NULL);
		struct tm *tmp = localtime(&t);
		FILE *f = fopen("heater_control.log", "a");
		if (f) {
			strftime(timestr, 50, "%F %T:", tmp);
			fprintf(f, "%s %s", timestr, str);
			fclose(f);
		}
		next_status_dump_at = time(NULL) + 15 * 60;
	}
}

int main(int argc, char** argv) 
{
	create_socket();
    setvbuf(stdin, NULL, _IONBF, 0);
	setvbuf(stdout, NULL, _IONBF, 0);

	while(1) {
		loop();
	}
	
	return 0;
}

