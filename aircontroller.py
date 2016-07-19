#!/usr/bin/python

import socket
import sys
import json
import time


sys.path.insert(0, '/var/scripts/aircontroller')
import acinterface as ac
import sleeptimer

stimer = sleeptimer.Sleep_Timer()	

# Create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Bind the socket to the port
server_address = ('192.168.1.6', 10000)
print >>sys.stderr, 'starting up on %s port %s' % server_address
sock.bind(server_address)

lastData = None

def sleep_ac(mins):

	global stimer
	
	if int(mins) == 0:
		stimer.stop_timer()
		
	stimer.start_timer(float(mins))
	
	return True
	
	
def get_schedule():

	global stimer
	
	d = {'Timer': str(stimer.get_status())}
	
	print "get_schedule: " + json.dumps(d)
	
	return json.dumps(d)
	
	
def getsettings():

	aircon = ac.AC_Unit()

	if aircon is None:
		return False
	
	d = {
		'Power': aircon.getPower(),
		'Mode': aircon.getMode(),
		'Fan': aircon.getFan(),
		'Temp': aircon.getTemp(),
		'CurrentTemp': aircon.getCurrentTemp()
		'TimeStamp': time.time() 
	}
	
	aircon = None
	
	lastData = json.dumps(d)
	
	return json.dumps(d)
	

def setsetting(cmd):

	aircon = ac.AC_Unit()
	
	print "Op: " + cmd['Operation']
	print "Type: " + cmd['Type']
	print "Value: " + cmd['Value']
	
	op_type = cmd['Type']
	
	if op_type == 'Power':
		aircon.setPower(cmd['Value'])
		
	elif op_type == 'Mode':
		aircon.setMode(cmd['Value'])
		
	elif op_type == 'Fan':
		aircon.setFan(cmd['Value'])
		
	elif op_type == 'Sleep':
		print "Setting sleep timer to: " + cmd['Value']
		sleep_ac(cmd['Value'])
		
	elif op_type == 'Temp':
		aircon.setTemp(cmd['Value'])
	
	aircon = None
	
	return True



if __name__ == "__main__":

	
		
	while True:
		print >>sys.stderr, '\nwaiting to receive message'
		data, address = sock.recvfrom(4096)

		print >>sys.stderr, 'received %s bytes from %s' % (len(data), address)
		print >>sys.stderr, data

		
		if data:
			try:
				command = json.loads(data)
				
				print command
				
				if command['Operation'] == "GET":
				
					if command['Type'] == "Settings":
						data = getsettings()
						if data is not False:
							sent = sock.sendto(data, address)
						else:
							sent = sock.sendto("failed", address)
					
					elif command['Type'] == "Schedule":
						
						print "Schedule request received"
						
						data = get_schedule()
						
						#print "sending" + data + " to " + address
						
						sent = sock.sendto(data, address)
						
						#if data is not False:
						#	sent = sock.sendto(data, address)
						#else:
							#sent = sock.sendto("failed", address)						
						
					print >>sys.stderr, 'sent %s bytes back to %s' % (sent, address)
				
				elif command['Operation'] == "SET":
					setsetting(command)
				else:
					print "Unexpected Data:"
					print data
			
			except:
				print "Not JSON"
				print data
				print ""

			
