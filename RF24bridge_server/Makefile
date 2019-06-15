CFLAGS		= -O3 -Wall -Werror
BIN		= /usr/local/bin
VERSION		= 1
SOURCEFILES	= dterm.c speeds.sh Makefile LICENCE.txt README.txt
READLINE	= -DREADLINE -lreadline

SRCS := dterm.c \
		cmdhandler.c \
		teleinfo_cksum.c rf24.c

OBJS := ${SRCS:.c=.o} 

dtermbridge: speeds.h ${OBJS}
	gcc ${OBJS} ${CFLAGS} -o dtermbridge -DVERSION='"$(VERSION)"' $(READLINE)

%.o: %.c Makefile
	${CC} ${CFLAGS} -c $<

speeds.h: speeds.sh
	sh speeds.sh >speeds.h

install:
	install dterm ${BIN}

clean:
	rm -f dterm speeds.h ${OBJS}  
