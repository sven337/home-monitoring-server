#!/usr/bin/python

import sys
import os
import fileinput

lines=sys.stdin.readlines()

oldtime=""
oldsplt=""
oldline=""
for line in lines:
	splt = line.split(':')
	time = splt[0]
	if time == oldtime:
		idx = splt[2]
		print(time + ':' + oldsplt[1] + ':' + splt[2])
		oldtime=""
		oldline=""
		time=""
		continue
	else:
		print(oldline)
	oldtime = time
	oldsplt = splt
	oldline = line
