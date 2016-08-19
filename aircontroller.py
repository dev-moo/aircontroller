#!/usr/bin/python

import socket
import sys
import json
import time
import threading
import Queue
import os
from time import sleep

sys.path.insert(0, '/var/scripts/aircontroller')
import acinterface as ac
import sleeptimer

#Globals
stimer = sleeptimer.Sleep_Timer()	
statusData = None
repeat_timer = None
update_interval = 1200

# Create a TCP/IP socket
sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

# Bind the socket to the port
server_address = ('192.168.1.6', 10000)
print >>sys.stderr, 'starting up on %s port %s' % server_address
sock.bind(server_address)

ac_address = '192.168.1.15'



class AC_Settings(object):

	def __init__(self):
		self.power = ''
		self.mode = ''
		self.fan = ''
		self.temp = ''
		self.currenttemp = ''
		self.timestamp = time.time()
		self.realtime = False
		self.online = False


def online(hostname):
	response = os.system("ping -c 1 " + hostname)
	
	if response == 0:
		return False
	
	return True
	
	
def convert_to_json(settings):

	data =  {
			'Power': settings.power,
			'Mode': settings.mode,
			'Fan': settings.fan,
			'Temp': settings.temp,
			'CurrentTemp': settings.currenttemp,
			'TimeStamp': settings.timestamp,
			'RealTime': str(setting.realtime),
			'Online': settings.online
		}	

	return json.dumps(data)
		

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
	
	
def getsettings(settings):
	
	if datetime.datetime.now() - settings.timestamp < 10:
		setting.realtime = False
		return settings
	
	aircon = ac.AC_Unit()

	if aircon is None:
		
		setting.realtime = False
		settings.online = online(ac_address)
		return settings
	
	
	settings.power = aircon.getPower(
	settings.mode = aircon.getMode()
	settings.fan = aircon.getFan()
	settings.temp = aircon.getTemp()
	settings.currenttemp = aircon.getCurrentTemp()
	settings.timestamp = time.time()
	setting.realtime = True ########
	settings.online = True
	
	aircon = None
	
	return settings
	
	


class Operate_AC(object):


	def __send_command(self, threading_event):
	
		i=1
		
		while not threading_event.isSet():
		
			if not self.cmd_queue.empty():
			
				cmd = self.cmd_queue.get()
				
				aircon = ac.AC_Unit()
				
				if aircon is not None:
					
					i=1
					
					op_type = cmd['Type']
					op_val = cmd['Value']
					
					if op_type == 'Power':
						
						aircon.setPower(op_val)
						
						sleep(5)
						
						if aircon.getPower() != op_val:
							self.cmd_queue.put(cmd)
							sleep(10)
							
						
					elif op_type == 'Mode':
					
						aircon.setMode(op_val)
						
						sleep(5)
						
						if aircon.getMode() != op_val:
							self.cmd_queue.put(cmd)
							sleep(10)
						
					elif op_type == 'Fan':
					
						aircon.setFan(op_val)
						
						sleep(5)
						
						if aircon.getFan() != op_val:
							self.cmd_queue.put(cmd)
							sleep(10)
						
					elif op_type == 'Temp':
					
						aircon.setTemp(op_val)
						
						sleep(5)
						
						if aircon.getTemp != op_val:
							self.cmd_queue.put(cmd)
							sleep(10)
						
					
				else:
					sleep(i*i)
					
				
				aircon = None
			
			else:
				sleep(1)
		
		return False
		
	
	def __init__(self):	
		self.cmd_queue = Queue.Queue()
		self.t_event = threading.Event()
		self.op_thread = threading.Thread(name='op_thread', target=self.__send_command, args=(self.t_event,))
		self.op_thread.start()
	
	
	def operate(self, command):
		print 'Adding new item to queue: ' + command
		self.cmd_queue.put(command)

	def kill(self):
		self.t_event.set()
		
	def __del__(self):
		pass
		
		

def setsetting(cmd, settings):

	
	print "Op: " + cmd['Operation']
	print "Type: " + cmd['Type']
	print "Value: " + cmd['Value']
	
	if 'RealTime' in cmd:
		pass
		#use forceful function
	
	if cmd['Type'] == 'Sleep':
		print "Setting sleep timer to: " + cmd['Value']
		sleep_ac(cmd['Value'])
	
	else:
		
		operator.operate(cmd)
		
		if cmd['Type'] == 'Power':
			settings.power = cmd['Value']
			
		elif cmd['Type'] == 'Mode':
			settings.mode = cmd['Value']
			
		elif cmd['Type'] == 'Fan':
			settings.fan = cmd['Value']
			
		elif cmd['Type'] == 'Temp':
			settings.temp = cmd['Value']
	
	return settings



#Call getsettings at a regular interval to keep status up to date and improve performance	
def updatesettings():

	global repeat_timer
	
	if statusData:
		t = json.loads(statusData)
		
		if time.time() - t['TimeStamp'] >= update_interval:
			getsettings()

	repeat_timer = None
	repeat_timer = threading.Timer(update_interval, updatesettings)
	repeat_timer.setName("update_settings_thread")
	repeat_timer.start()


#updatesettings()



if __name__ == "__main__":


	AC = AC_Settings()
	operator = Operate_AC()

	try:
		
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
							
							AC = getsettings(AC)
							
							data = convert_to_json(AC)
							
							sent = sock.sendto(data, address)
						
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
						t = threading.Thread(target=setsetting, args=(command,))
						t.start()
					else:
						print "Unexpected Data:"
						print data
				
				except:
					print "Not JSON"
					print data
					print ""
					
	finally:
		operator.kill()
			
