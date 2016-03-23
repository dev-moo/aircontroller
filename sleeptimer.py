#!/usr/bin/python

import threading
import time
import sys
from time import sleep

sys.path.insert(0, '/var/scripts/aircontroller')
import acinterface as ac
import kill_climate_control

class Sleep_Timer(object):

	def stop_timer(self):
		print "Stopping Timer"
		try:
			self.sleeptimer.cancel()
		except:
			return False

		return True
		

	def __power_off(self):
		
		print "Power off A/C"
		
		self.stop_timer()
		self.sleeptimer = None
		
		for i in xrange(1, 3):
			kill_climate_control.kill_cc()
			sleep(1)
		
		for i in xrange(1, 50):
			
			aircon = ac.AC_Unit()

			if aircon is not None:
				aircon.setPowerOff()
				
				sleep(5)
				
				if aircon.getPower() == "Off":
					aircon = None
					return True
			
			aircon = None
			
			sleep(i*i)
			
		return False

		
	def __is_timer_running(self):
		
		for tds in threading.enumerate():
			if tds.getName() == "SleepThread":
				print "Timer is already active"
				return True
				
		return False
		
	def start_timer(self, minutes):

		seconds = minutes * 60
		
		if self.__is_timer_running():
			return False

		try:
			self.sleeptimer = threading.Timer(seconds, self.__power_off)
			self.sleeptimer.setName("SleepThread")
			self.sleeptimer.start()
			
			print "Timer started " + seconds
			
		except:
			return False

		return True

		
	def get_status(self):
		return self.__is_timer_running()
		
		
	def __init__(self):
		self.sleeptimer = None
	
	def __del__(self):
		self.stop_timer()
		
		
		
if __name__ == '__main__':
	
	st = Sleep_Timer()
	
	print "Status: " + str(st.get_status())
	
	print "Starting Timer"
	st.start_timer(10)
	sleep(5)
	st.stop_timer()
	
	
	
	
	