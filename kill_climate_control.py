#!/usr/bin/python

import socket
import json
from time import sleep


def kill_cc():
	address = ('192.168.1.3', 10001)

	sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

	d = {'OP': 'STOP'}
											
	send = sock.sendto(json.dumps(d), address)	

if __name__ == "__main__":
	
	for i in xrange(1, 3):
		kill_cc()
		sleep(2)
	