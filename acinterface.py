#!/usr/bin/python

import xml.etree.ElementTree as ET
import OpenSSL
import socket
import struct
import ConfigParser
import os
from time import sleep


class AC_Unit(object):

	def __getACConnection(self):
		# Prefer TLS
		context = OpenSSL.SSL.Context(OpenSSL.SSL.TLSv1_METHOD)
		s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
		s.settimeout(10)
		connection = OpenSSL.SSL.Connection(context,s)
		connection.connect((self.addr, int(self.port)))

		# Put the socket in blocking mode
		connection.setblocking(1)

		# Set the timeout using the setsockopt
		tv = struct.pack('ii', int(6), int(0))
		connection.setsockopt(socket.SOL_SOCKET, socket.SO_RCVTIMEO, tv)

		print "Connected to " , connection.getpeername()
		print "State " , connection.state_string()

		try:
			connection.do_handshake()
		except OpenSSL.SSL.WantReadError:
			print "Connection Timeout"
			return None

		print "State ", connection.state_string()

		return connection


	def __createConnectionReq(self):
		connectstr = """<?xml version="1.0" encoding="utf-8" ?><Request Type="AuthToken"><User Token="%usertoken%" /></Request>"""
		return connectstr.replace("%usertoken%", self.token)

	def __createStatusReq(self):
		statusstr = """<?xml version="1.0" encoding="utf-8" ?><Request Type="DeviceState" DUID="%ACDUID%" />"""
		return statusstr.replace("%ACDUID%", self.duid)

	def __createControlReq(self, function, value):
		root = ET.Element('Request', Type="DeviceControl")
		child = ET.SubElement(root, 'Control', CommandID="cmd00000", DUID=self.duid)
		grandchild = ET.SubElement(child, 'Attr', ID=function, Value=value)
		return self.xmlheader + ET.tostring(root)

	def parseResponse(self, xmlstr, attrib):
		xmltree = ET.ElementTree(ET.fromstring(xmlstr))
		for node in xmltree.iter():
			for n in node.keys():
				if n == "ID" and node.get(n) == attrib: 
					return node.get('Value')
		return None
		
	def __checkResponse(self, xmlstr, type):
	
		#print "XMLSTR:"
		#print xmlstr
		#print ""
		
		if xmlstr is None:
			return False
		
		if self.xmlheader not in xmlstr:
			return False
	
		if xmlstr == None:
			return False
			
		xmltree = ET.ElementTree(ET.fromstring(xmlstr))
		for node in xmltree.iter():
			if node.tag == 'Response' and node.get('Type') == type and node.get('Status') == 'Okay':
				return True 
		return False		

	def __receive(self):
		try:
			recvstr = self.con.recv(1024)
		except OpenSSL.SSL.WantReadError:
			print "Timeout"
			return None

		return recvstr
        
	def __transmit(self, data):
		self.con.send(data + "\r\n")
		
		
	def __setSetting(self, command, type):
		
		for num in range(1,3):
			#print "Transmitting"
			#print command
			#print ""
			self.__transmit(command)
			sleep(1)
			
			for num in range(1,3):
				res = self.__receive()
				#print "Response"
				#print res
				#print ""
				
				if self.__checkResponse(res, type):
					return True
		
		return False
		
	def __getSetting(self, setting):
		
		for num in range(1,3):
			self.__transmit(self.__createStatusReq())
			response = self.__receive()
			
			if self.__checkResponse(response, 'DeviceState'):
				return self.parseResponse(response, setting)
			
			for num in range(1,5):
				if self.__receive() == None:
					break
			
		return None		
		

	def __authenticate(self):
		return self.__setSetting(self.__createConnectionReq(), 'AuthToken')

        
		
	def __closeConnection(self):
		self.__transmit("close")

	def __init__(self):

		configFile = '/var/scripts/aircontroller/ac-connect.conf'

		# Check config file exists	
		if not os.path.isfile(configFile):
			print ("Error - Missing Config File: " + configFile)
			quit()

		# Get config	
		config = ConfigParser.ConfigParser()
		config.read(configFile)

		self.addr = config.get('ac_settings', 'ac_addr')
		self.port = config.get('ac_settings', 'ac_port')
		self.duid = config.get('ac_settings', 'duid')
		self.token = config.get('ac_settings', 'user_token')
		self.xmlheader = """<?xml version="1.0" encoding="utf-8" ?>"""
		self.con = self.__getACConnection()
		
		if self.con == None:
			print "Error: Unable to establish a connection to A/C unit"
			return None
			
		if not self.__authenticate():
			print "Error: Unable to authenticate with A/C unit"
			return None


	def __del__(self):
		if self.con != None:
			self.__closeConnection()


	def showSettings(self):
		print "Settings:"
		print self.addr
		print self.port
		print self.duid
		print self.token
		print ""

		
	def sanityCheck(self, options, value):
		
		for op in options:
			if "%s" % op == value.lower():
				return True
		
		return False
		
		
	def rec(self):
		return self.__receive()
		
		
	def setPower(self, val):
		operations = ['on', 'off']
		if self.sanityCheck(operations, val):
			return self.__setSetting(self.__createControlReq("AC_FUN_POWER", val), 'DeviceControl')
		return False		
	
	def setMode(self, val):
		if val == 'Fan':
			val = 'Wind'
			
		operations = ['auto', 'cool', 'dry', 'wind', 'heat']
		if self.sanityCheck(operations, val):
			return self.__setSetting(self.__createControlReq("AC_FUN_OPMODE", val), 'DeviceControl')
		return False

	def setFan(self, val):
		operations = ['low', 'mid', 'high', 'auto']
		if self.sanityCheck(operations, val):
			return self.__setSetting(self.__createControlReq("AC_FUN_WINDLEVEL", val), 'DeviceControl')		
		return False

	def setTemp(self, val):
		return self.__setSetting(self.__createControlReq("AC_FUN_TEMPSET", val), 'DeviceControl')
		
	def setPowerOn(self):
		return self.setPower('On')

	def setPowerOff(self):
		return self.setPower('Off')
		
		
	def getStatus(self):
		self.__transmit(self.__createStatusReq())
		return self.__receive()

	def getUserToken(self):
		tkncmd = """<?xml version="1.0" encoding="utf-8" ?><Request Type="GetToken" />"""
		self.__transmit(tkncmd)
		return self.__receive()

	def getPower(self):
		return self.__getSetting('AC_FUN_POWER')
		#self.__transmit(self.__createStatusReq())
		#return self.parseResponse(self.__receive(), 'AC_FUN_POWER')

	def getTemp(self):
		return self.__getSetting('AC_FUN_TEMPSET')
		#self.__transmit(self.__createStatusReq())
		#return self.parseResponse(self.__receive(), 'AC_FUN_TEMPSET')

	def getMode(self):
		self.__transmit(self.__createStatusReq())
		m = self.parseResponse(self.__receive(), 'AC_FUN_OPMODE')
		if m == 'Wind':
			m = 'Fan'
		return m
		
	def getFan(self):
		self.__transmit(self.__createStatusReq())
		return self.parseResponse(self.__receive(), 'AC_FUN_WINDLEVEL')

	def getCurrentTemp(self):
		self.__transmit(self.__createStatusReq())
		temp = int(self.parseResponse(self.__receive(), 'AC_FUN_TEMPNOW'))
		celcius = round((temp - 32) * 5.0/9.0, 1)
		return str(celcius)


        
if __name__ == "__main__":
	
	aircon = AC_Unit()
	
	if aircon == None:
		print "Connection failed :("
		exit()
	
	print "Starting:"
	
	print "Power:        " + aircon.getPower()
	print "Temp:         " + aircon.getTemp()
	print "Mode:         " + aircon.getMode()
	print "Fan:          " + aircon.getFan()
	print "Current Temp: " + aircon.getCurrentTemp()
	print ""
	
	print "Changing Settings"
	#print "Set temp:  " + str(aircon.setTemp("28"))
	print "Set power: " + str(aircon.setPower("On"))
	#print "Set mode:  " + str(aircon.setMode("Wind"))
	print "Set fan:   " + str(aircon.setFan("Low"))
	
	
	print ""
	print "Power:        " + aircon.getPower()
	print "Temp:         " + aircon.getTemp()
	print "Mode:         " + aircon.getMode()
	print "Fan:          " + aircon.getFan()
	print "Current Temp: " + aircon.getCurrentTemp()
		
	#print aircon.getStatus()

	#aircon.setPower("Off")
	
	aircon = None

	print ""
	print "Seeya"




