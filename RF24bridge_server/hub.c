#include <stdlib.h>
#include <arpa/inet.h>
#include <netinet/in.h>
#include <stdio.h>
#include <sys/types.h>
#include <sys/socket.h>
#include <unistd.h>
#include <string.h>

#define PORT 45888

int udp_hub_sockfd;

static struct sockaddr_in *clients[10];

int udp_hub_init(void)
{
	struct sockaddr_in si_me;

	udp_hub_sockfd = socket(AF_INET, SOCK_DGRAM, IPPROTO_UDP);
	if (udp_hub_sockfd == -1) {
		perror("socket");
		exit(1);
	}

	memset(&si_me, 0, sizeof(si_me));
	si_me.sin_family = AF_INET;
	si_me.sin_port = htons(PORT);
	si_me.sin_addr.s_addr = htonl(INADDR_ANY);

	if (bind(udp_hub_sockfd, (struct sockaddr *)&si_me, sizeof(si_me)) == -1) {
		perror("bind");
		exit(1);
	}

	printf("UDP socket %d\n", udp_hub_sockfd);

	return 0;
}

static int find_client(unsigned long addr)
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


static int add_client(struct sockaddr_in *si)
{
	unsigned int i;
	int index = find_client(si->sin_addr.s_addr);
	if (index != -1)
		// Client already registered, nothing to do
		return 1;

	for (i = 0; i < sizeof(clients)/sizeof(clients[0]); i++) {
		if (!clients[i]) {
			// Found a free slot
			clients[i] = calloc(1, sizeof(struct sockaddr_in));
			memcpy(clients[i], si, sizeof(struct sockaddr_in));
			return 0;
		}
	}
	return 0;
}

char *udp_hub_consume(void) 
{
	struct sockaddr_in si_from;
	unsigned int addr_len = sizeof(struct sockaddr_in);
	const int BUFLEN = 4096;
	static char *buf = NULL;

	if (!buf) {
		buf = malloc(BUFLEN);
	}

	int sz = 0;
	sz = recvfrom(udp_hub_sockfd, buf, BUFLEN, 0, (struct sockaddr *)&si_from, &addr_len);

	if (sz == -1) {
		perror("recvfrom");
		return "";
	}
	buf[sz] = 0;

	printf("UDP command %s from %s\n", buf, inet_ntoa(si_from.sin_addr));
	if (si_from.sin_family != AF_INET) {
		// Localhost comes from netlink and not UDP, why the hell?!
		return "";
	}
	
	add_client(&si_from);

	return buf;
}

void udp_hub_send_to_clients(const char *buf, int len)
{
	unsigned int i;
	for (i = 0; i < sizeof(clients)/sizeof(clients[0]); i++) {
		if (clients[i]) {
			if (sendto(udp_hub_sockfd, buf, len, 0, (struct sockaddr *)clients[i], sizeof(struct sockaddr_in)) == -1) {
				perror("sendto");
				return;
			}
		}
	}
}

