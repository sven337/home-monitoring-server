CFLAGS		= -O3 -Wall -Werror
BIN		= /usr/local/bin
VERSION		= 1
SOURCEFILES	= dterm.c speeds.sh Makefile LICENCE.txt README.txt
READLINE	= -DREADLINE -lreadline
MQTT_LIBS	= -lmosquitto

SRCS := dterm.c \
		cmdhandler.c \
		rf24.c

OBJS := ${SRCS:.c=.o} 

dtermbridge: speeds.h ${OBJS} 
	gcc ${OBJS} ${CFLAGS} -o dtermbridge -DVERSION='"$(VERSION)"' $(READLINE) $(MQTT_LIBS)

%.o: %.c Makefile
	${CC} ${CFLAGS} -c $<

speeds.h: speeds.sh
	sh speeds.sh >speeds.h

install:
	install dtermbridge ${BIN}

clean:
	rm -f dtermbridge speeds.h ${OBJS}  
