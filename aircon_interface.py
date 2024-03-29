"""Talk to A/C WIFI Module"""

import sys
import os
import socket
import OpenSSL
import select
import struct
import xml.etree.ElementTree as ET
import time
from time import sleep
import threading

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, THIS_DIR)

import get_config
import log_handler
import pollable_queue


#Global Constants
CONFIG_FILE_NAME = 'aircontroller_config.txt'

MAX_TRIES = 50
XML_HEADER = """<?xml version="1.0" encoding="utf-8" ?>"""
SHUTDOWN_CMD = 'DIE'
STATUS_POLL_FREQ = 60 #seconds
RESPONSE_WAIT_TIME = 5 #seconds

#A/C Properties
AC_POWER = 'AC_FUN_POWER'
AC_MODE = 'AC_FUN_OPMODE'
AC_FAN = 'AC_FUN_WINDLEVEL'
AC_TEMP = 'AC_FUN_TEMPSET'
AC_CURRENT_TEMP = 'AC_FUN_TEMPNOW'
AC_AUTH_TOKEN = 'AuthToken'

AC_RESPONSE_TYPE = 'Type'
AC_RESPONSE_ID = 'ID'
AC_RESPONSE_VALUE = 'Value'
AC_RESPONSE_STATUS = 'Status'

AC_RESPONSE_TYPE_DSTATE = 'DeviceState'
#AC_RESPONSE_TYPE_AUTH = 'AuthToken'
AC_RESPONSE_TYPE_STATUS = 'Status'


VALID_OPERATIONS = {AC_POWER: ('On', 'Off'),
                    AC_MODE: ('Auto', 'Cool','Dry', 'Wind', 'Heat'),
                    AC_FAN: ('Low', 'Mid', 'High', 'Auto'),
                    AC_TEMP: (tuple(range(16, 31))),
                    AC_CURRENT_TEMP: ('Not used'),
                    AC_AUTH_TOKEN: ('Okay')}

STATUS_CONTAINER = dict.fromkeys(VALID_OPERATIONS, '')

LAST_UPDATE = 'LAST_UPDATE'


AC_CONNECTION_STATUS = 'AC_CONNECTION_STATUS'
AC_CONN_STATUS_ONLINE = 'ONLINE'
AC_CONN_STATUS_CACHED = 'CACHED'
AC_CONN_STATUS_OFFLINE = 'OFFLINE'

STATUS_CONTAINER[LAST_UPDATE] = float(0)
STATUS_CONTAINER[AC_CONNECTION_STATUS] = AC_CONN_STATUS_ONLINE

POWER = 'POWER'
MODE = 'MODE'
FAN = 'FAN'
TEMP = 'TEMP'
CURRENT_TEMP = 'CURRENT_TEMP'
AUTHENTICATION = 'AUTHENTICATION'

TRANSLATE = {AC_POWER: POWER,
             AC_MODE: MODE,
             AC_FAN: FAN,
             AC_TEMP: TEMP,
             AC_CURRENT_TEMP: CURRENT_TEMP,
             AC_AUTH_TOKEN: AUTHENTICATION}



class ACCommunications(object):

    """Maintain reliable communications to A/C WIFI module"""

    def __create_authentication_request(self):
        """XML string required to authenticate with A/C server"""
        return """%s<Request Type="AuthToken"><User Token="%s" /></Request>""" % (XML_HEADER, self.token)

    
    def __disconnect(self):
    
        """Disconnect SSL connection"""
        
        self.logger2.info('Disconnecting SSL session')
        
        if not self.ssl_con:
            return True
        
        try:
            self.__send_data('exit')
            sleep(1)
        except:
            pass
        
        try:
            self.ssl_con.shutdown()
            self.ssl_con.close()
        except:
            pass
            
        self.ssl_con = None   
         
        if self.ssl_con:
            self.logger2.warning('Disconnect SSL failed')
            return False
            
        self.logger2.debug('Disconnected SSL session')

        return True
        
    
    def __send_data(self, data):

        """Send data on SSL connection"""

        self.logger2.debug('Sending some data to A/C')

        try:
            data = self.ssl_con.send((data + '\r\n').encode())
            return True
        except:
            self.logger2.exception('Exception sending data on socket')

        return False


    def __receive_data(self):

        """Receive data on SSL connection"""

        self.logger2.debug('Receiving some data from A/C')

        try:
            #self.logger2.debug('Number of bytes in receive buffer: %s', self.ssl_con.pending())
            data = self.ssl_con.recv(1024)
            data = data.decode()
            return data.strip('\r''\n')
        except:
            self.logger2.exception('Exception receiving data on socket')

        return None


    def __get_ssl_connection(self):

        """Get SSL connection to A/C unit"""
        
        self.ssl_con = None
        
        self.logger2.debug('Connecting to %s...', self.server_address)

        # Prefer TLS
        context = OpenSSL.SSL.Context(OpenSSL.SSL.TLSv1_METHOD)
        context.set_cipher_list('AES256-SHA')
        
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #sock.settimeout(5)
        connection = OpenSSL.SSL.Connection(context, sock)
        
        try:
            connection.connect(self.server_address)
        except Exception as e:
            self.logger2.exception('Unable to connect to A/C: %s %s', e.message, e.args)
            self.ssl_con = None
            del sock
            del connection
            return False

        # Put the socket in blocking mode
        connection.setblocking(1)

        # Set the timeout using the setsockopt
        connection.setsockopt(socket.SOL_SOCKET,
                              socket.SO_RCVTIMEO,
                              struct.pack('ii', int(6), int(0)))

        self.logger2.debug('Connected to %s', connection.getpeername())

        try:
            connection.do_handshake()
        #except OpenSSL.SSL.WantReadError:
        except Exception as e:
            self.logger2.exception('Handshake failed %', connection.state_string())
            connection.close()
            self.ssl_con = None
            del sock
            del connection
            return False

        #self.logger2.debug('State %s', connection.state_string())
        self.ssl_con = connection
        self.tx_queue.put(self.__create_authentication_request())

        return True

       
        
    def __establish_ssl_connection(self):

        """Loop until SSL connection established, increase wait time on each loop"""
        
        self.logger2.info('Attempting to establish connection with A/C...')
        
        try:
            if self.ssl_con: self.__disconnect()
        except:
            self.logger2.info('Exception during disconnect')

        for num in range(MAX_TRIES):
            
            try: 
                if self.__get_ssl_connection():
                    self.logger2.info('A/C connection established')
                    return True
            
            except:
                self.logger2.info('Exception while establishing SSL')
                
                
            self.logger2.info('Unable to establish SSL connection, retrying in %d seconds', num * num + num)
            sleep(num * num + num)

        self.logger2.critical('Unable to establish SSL connection within allowed number of attempts')
        
        #Shutdown
        self.__del__()
        

    def __monitor_socket(self):

        """
        Monitor incoming data on SSL connection and transmit queue
        """

        self.logger2.debug('Starting SSL connection monitoring')

        #self.__maintain_ssl_connection()
        self.__establish_ssl_connection()

        inputs = [self.ssl_con, self.tx_queue]

        while True:

            try:
                readable, writable, exceptional = select.select(inputs, [], [])

                for s in readable:

                    #Check SSL connection is in select
                    if not self.ssl_con in inputs:
                        inputs.append(self.ssl_con)
                    
                    #Check number of inputs in select
                    if len(inputs) != 2:
                        self.logger2.warning('Number of select inputs is: %d', len(inputs))
                    
                    #If input from SSL Connection
                    if s is self.ssl_con:
                    
                        data = self.__receive_data()

                        if data:
                            self.logger2.debug('Putting received data on rx_queue')
                            self.rx_queue.put(data)
                        else:
                            self.logger2.warning('Error receiving data from A/C')
                            inputs.remove(s)
                            self.__establish_ssl_connection()                       
                    
                    #If input from transmit queue
                    elif s is self.tx_queue:
                    
                        self.logger2.debug('Getting data from tx_queue')

                        data = self.tx_queue.get()

                        if data == SHUTDOWN_CMD:
                            self.logger2.info('Shutdown command received, ending connection monitoring')
                            self.__del__()
                            return None

                        #Transmit to A/C
                        if self.__send_data(data):
                            self.logger2.debug('Data sent successfully')
                        else:
                            inputs.remove(s)
                            self.__establish_ssl_connection()
                            #inputs.append(self.ssl_con)
                            #readable, writable, exceptional = select.select(inputs, [], inputs)
                    
                    #If input from unexpected source
                    else:
                        self.logger2.warning('readable input in select is not monitored, removing: %s', str(s))
                        inputs.remove(s)

                for s in exceptional:
                    self.logger2.exception('Select returned an exceptional event')

            except Exception as e:
                #self.logger2.exception('Exception at select.select: %s %s', e.message, e.args)
                self.logger2.exception('Exception at select.select')
                break

        self.logger2.critical('Connection monitoring ended unexpectedly')
        #Shutdown
        self.__del__()

    
    def reset_ssl(self):
    
        self.__disconnect()
        
        #self.reset_timer = threading.Timer(self.reset_period, self.reset_ssl) 
        #self.reset_timer.start() 



    def __init__(self, s_address, token, send_q, receive_q, log):

        """Setup socket monitoring"""

        self.server_address = s_address
        self.token = token
        self.tx_queue = send_q
        self.rx_queue = receive_q
        self.logger2 = log
        
        self.reset_period = 90

        self.ssl_con = None
        self.monitor_socket = None

        self.start()

        #self.monitor_socket = threading.Thread(name='monitor_ssl_socket',
        #                                      target=self.__monitor_socket)
        #self.monitor_socket.start()
        
        #self.reset_timer = threading.Timer(self.reset_period, self.reset_ssl) 
        #self.reset_timer.start() 
        
    def start(self):
        
        self.monitor_socket = threading.Thread(name='monitor_ssl_socket',
                                               target=self.__monitor_socket)
        self.monitor_socket.start()
        
    def stop(self):
        self.__del__()

    def __del__(self):
        self.logger2.info('Deconstructing ACCommunications')
        self.__disconnect()
        self.tx_queue.put(SHUTDOWN_CMD)
        #self.rx_queue.put(SHUTDOWN_CMD)

    def shutdown(self):
        self.__del__()




class AirConInterface(object):

    """Provide methods to control A/C unit"""

    def __create_status_request(self):
        """XML string to get current status of A/C"""
        return """%s<Request Type="DeviceState" DUID="%s" />""" % (XML_HEADER, self.ac_duid)


    def __create_control_request(self, function, value):

        """Generate XML request to update a setting on A/C"""

        root = ET.Element('Request', Type="DeviceControl")
        child = ET.SubElement(root, 'Control', CommandID="cmd00000", DUID=self.ac_duid)
        grandchild = ET.SubElement(child, 'Attr', ID=function, Value=value)
        #print(type(XML_HEADER))
        #print(type(ET.tostring(root)))
        return XML_HEADER + (ET.tostring(root)).decode()


    def __parse_xml_input(self, xml_string):

        """parse xml responses from A/C to a list of dicts"""

        try:

            root = ET.fromstring(xml_string)

            if root.attrib[AC_RESPONSE_TYPE] == AC_AUTH_TOKEN:
                return [{AC_RESPONSE_TYPE: root.attrib[AC_RESPONSE_TYPE],
                         AC_RESPONSE_ID: AC_AUTH_TOKEN,
                         AC_RESPONSE_VALUE: root.attrib[AC_RESPONSE_STATUS]}]

            else:

                func, value, all_attributes = None, None, []

                for node in root.iter():

                    for n in node.keys():

                        if n == AC_RESPONSE_ID:
                            func = node.get(n)
                        elif n == AC_RESPONSE_VALUE:
                            value = node.get(n)

                    if func in VALID_OPERATIONS.keys():
                        all_attributes.append({AC_RESPONSE_TYPE: root.attrib[AC_RESPONSE_TYPE],
                                               AC_RESPONSE_ID: func,
                                               AC_RESPONSE_VALUE: value})

                return all_attributes


        except ET.ParseError:
            self.logger1.debug('Error parsing XML - ET.ParseError')
        except KeyError:
            self.logger1.debug('Error parsing XML - KeyError')

        return None


    def __update_status_contatiner(self, function, value):

        """Update current status container"""

        if function in self.status:
            if function == AC_MODE and value == 'Wind': value = 'Fan'
            self.status[function] = value
            return True
        else:
            #self.logger1.exception('Error updating current status dict, no key:', function)
            return False


    def __monitor_input(self, r_event):

        """Thread to monitor incoming data from A/C"""

        self.logger1.debug('Starting monitoring of receive queue')

        while True:

            try:
                readable = select.select([self.rx_queue], [], [])

                if readable[0]:

                    self.logger1.debug('Getting data from receive queue')

                    data = self.rx_queue.get()

                    if data == SHUTDOWN_CMD:
                        self.logger1.info('Shutting down monitoring of receive queue')
                        return None

                    parsed = self.__parse_xml_input(data)

                    if isinstance(parsed, list):
                        for attrib in parsed:
                            self.__update_status_contatiner(attrib[AC_RESPONSE_ID],
                                                            attrib[AC_RESPONSE_VALUE])

                        #received full status update
                        if len(parsed) > 0 and parsed[0][AC_RESPONSE_TYPE] == AC_RESPONSE_TYPE_DSTATE:
                            self.__update_status_contatiner(LAST_UPDATE, time.time())
                            r_event.set()

            except TypeError:
                break
            except:
                self.logger1.exception('Exception:')

        self.logger1.info('Monitoring of receive queue ended unexpectedly')
        self.__del__()



    def __poll_status(self):

        """Request A/C status at a regular interval"""

        if self.tx_queue:
            self.tx_queue.put(self.__create_status_request())
        else:
            self.logger1.info('Stopping poll_status thread')
            return None

        self.polling_thread = threading.Timer(STATUS_POLL_FREQ, self.__poll_status)
        self.polling_thread.setName('status_polling_thread')
        self.polling_thread.start()



    def __init__(self):

        config = get_config.get_config(CONFIG_FILE_NAME)

        log_filename = THIS_DIR + '/' + config.get('interface', 'logfile')
        ac_address = (config.get('interface', 'ac_addr'),
                      int(config.get('interface', 'ac_port')))

        ac_token = config.get('interface', 'user_token')

        self.ac_duid = config.get('interface', 'duid')
        self.receive_event = threading.Event() #Set when status update received
        self.status = STATUS_CONTAINER

        self.logger1 = log_handler.get_log_handler(log_filename, 'info', 'ac.interface')
        self.logger2 = log_handler.get_log_handler(log_filename, 'info', 'ac.comms')

        self.logger1.info('Starting: AirConInterface')

        #Send to A/C
        self.tx_queue = pollable_queue.PollableQueue()
        #Receive from A/C
        self.rx_queue = pollable_queue.PollableQueue()

        self.logger1.debug('Setting up communications with A/C WIFI module')
        self.ac_con = ACCommunications(ac_address,
                                       ac_token, self.tx_queue,
                                       self.rx_queue, self.logger2)

        #Wait for input from ACCommunications, then continue
        select.select([self.rx_queue], [], [])

        self.logger1.info('Established communications with A/C WIFI module')

        #Start thread to monitor receive queue
        self.monitor_input = threading.Thread(name='monitor_input',
                                              target=self.__monitor_input,
                                              args=(self.receive_event,))
        self.receive_event.clear()
        self.monitor_input.start()

        #Start thread to poll A/C status
        self.polling_thread = None
        self.__poll_status()



    def __del__(self):
        self.logger1.info('Shutting down all everything!')
        self.tx_queue.put(SHUTDOWN_CMD)
        self.rx_queue.put(SHUTDOWN_CMD)
        self.polling_thread.cancel()
        sleep(2)
        #del self.tx_queue
        #del self.rx_queue
        self.logger1.info('Shutdown of all everything complete, goodbye :)')


    def kill(self):
        self.__del__()

    def shutdown(self):
        self.__del__()


    #Translate self.status dictionary key names
    def __translate(self):
        status_dict = self.status.copy()
        
        for key in TRANSLATE.keys():
            status_dict[TRANSLATE[key]] = status_dict.pop(key)

        #Provide feedback on age of status info
        if time.time() - status_dict[LAST_UPDATE] < 5:
            status_dict[AC_CONNECTION_STATUS] = AC_CONN_STATUS_ONLINE
        elif time.time() - status_dict[LAST_UPDATE] <= 60:
            status_dict[AC_CONNECTION_STATUS] = AC_CONN_STATUS_CACHED
        else:
            status_dict[AC_CONNECTION_STATUS] = AC_CONN_STATUS_OFFLINE
            
        return status_dict

    def get_all_settings(self):
        self.logger1.debug('Requesting A/C current status')
        self.receive_event.clear()
        self.tx_queue.put(self.__create_status_request())

        #Wait for response
        self.receive_event.wait(RESPONSE_WAIT_TIME)

        if self.receive_event.isSet():
            self.logger1.debug('Received data from A/C')
        else:
            self.logger1.info('No data received, returning cached data')

        return self.__translate()

    def get_power(self):
        self.get_all_settings()
        return self.status[AC_POWER]

    def get_mode(self):
        self.get_all_settings()
        return self.status[AC_MODE]

    def get_fan(self):
        self.get_all_settings()
        return self.status[AC_FAN]

    def get_temp(self):
        self.get_all_settings()
        return self.status[AC_TEMP]

    def get_current_temp(self):
        self.get_all_settings()
        return self.status[AC_CURRENT_TEMP]


    def __set(self, function, val, possible_vals):
        """sanity check request and add to transmit queue"""
        if isinstance(val, str): val = val.capitalize()
        
        if val in possible_vals:
            if not isinstance(val, str): val = str(val)
            self.__update_status_contatiner(function, val)
            self.tx_queue.put(self.__create_control_request(function, val))
            return True
        
        return False

    def set_power(self, val):
        self.logger1.debug('Setting power to: %s', val)
        self.__set(AC_POWER, val, VALID_OPERATIONS[AC_POWER])

    def set_mode(self, val):
        if val == 'FAN': val = 'Wind'
        self.logger1.debug('Setting mode to: %s', val)
        self.__set(AC_MODE, val, VALID_OPERATIONS[AC_MODE])

    def set_fan(self, val):
        self.logger1.debug('Setting fan to: %s', val)
        self.__set(AC_FAN, val, VALID_OPERATIONS[AC_FAN])

    def set_temp(self, val):
        self.logger1.debug('Setting temp to: %s', val)
        self.__set(AC_TEMP, int(val), VALID_OPERATIONS[AC_TEMP])

    def set_power_on(self):
        self.set_power('On')

    def set_power_off(self):
        self.set_power('Off')
