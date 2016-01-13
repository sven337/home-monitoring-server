#!/bin/bash 

echo $1 | nc -w 1 -q 1 -u 192.168.0.6 45889
