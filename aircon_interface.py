"""Talk to A/C WIFI Module"""

import sys
import os
import socket
import OpenSSL
import select
import struct
import xml.etree.ElementTree as ET
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

AC_POWER = 'AC_FUN_POWER'
AC_MODE = 'AC_FUN_OPMODE'
AC_FAN = 'AC_FUN_WINDLEVEL'
AC_TEMP = 'AC_FUN_TEMPSET'
AC_CURRENT_TEMP = 'AC_FUN_TEMPNOW'
AC_AUTH_TOKEN = 'AuthToken'

VALID_OPERATIONS = {AC_POWER: ('On', 'Off'),
                    AC_MODE: ('Auto', 'Cool','Dry', 'Wind', 'Heat'),
                    AC_FAN: ('Low', 'Mid', 'High', 'Auto'),
                    AC_TEMP: (tuple(range(16, 31))),
                    AC_CURRENT_TEMP: ('Not used'),
                    AC_AUTH_TOKEN: ('Okay')}

STATUS_CONTAINER = dict.fromkeys(VALID_OPERATIONS, '')


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


    def __send_data(self, data):

        """Send data on SSL connection"""

        self.logger2.debug('Sending some data to A/C')

        try:
            data = self.ssl_con.send(data + '\r\n')
            return True
        except:
            self.logger2.exception('Exception sending data on socket')

        return False


    def __receive_data(self):

        """Receive data on SSL connection"""

        self.logger2.debug('Receiving some data from A/C')

        try:
            data = self.ssl_con.recv(1024)
            return data.strip('\r''\n')
        except:
            self.logger2.exception('Exception receiving data on socket')

        return None


    def __get_ssl_connection(self):

        """Get SSL connection to A/C unit"""

        # Prefer TLS
        context = OpenSSL.SSL.Context(OpenSSL.SSL.TLSv1_METHOD)
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        sock.settimeout(5)
        connection = OpenSSL.SSL.Connection(context, sock)
        connection.connect(self.server_address)

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
        except:
            self.logger2.exception('Handshake failed %', connection.state_string())
            connection.close()
            self.ssl_con = None
            return False

        self.logger2.debug('State %s', connection.state_string())
        self.ssl_con = connection
        self.tx_queue.put(self.__create_authentication_request())

        return True



    def __test_connection(self):

        """Test SSL connection is up"""

        #return True

        try:
            self.ssl_con.do_handshake()
        #except OpenSSL.SSL.WantReadError:
        except:
            self.logger2.info('Testing of SSL connection failed')
            return False

        self.logger2.debug('Testing of SSL connection passed')
        return True


    def __maintain_ssl_connection(self):

        """Loop until SSL connection established, increase wait time on each loop"""

        if self.ssl_con and self.__test_connection():
            return True

        for num in xrange(MAX_TRIES):
            self.__get_ssl_connection()
            if self.ssl_con:
                return True
            self.logger2.debug('Unable to establish SSL connection, retrying in %d seconds', num * num)
            sleep(num * num)

        self.logger2.critical('Unable to establish SSL connection within allowed number of attempts')
        return False


    def __monitor_socket(self):

        """
        Monitor incoming data on SSL connection and transmit queue
        """

        self.logger2.debug('Starting SSL connection monitoring')

        self.__maintain_ssl_connection()

        inputs = [self.ssl_con, self.tx_queue]

        while True:

            try:
                readable, writable, exceptional = select.select(inputs, [], inputs)

                for s in readable:

                    if s is self.ssl_con:
                        data = self.__receive_data()

                        if data:
                            self.logger2.debug('Putting data on rx_queue')
                            self.rx_queue.put(data)
                        else:
                            self.logger2.warning('Error receiving data?')

                    if s is self.tx_queue:
                        self.logger2.debug('Getting data from tx_queue')

                        #confirm connection before trying to send anything
                        self.__maintain_ssl_connection()

                        data = self.tx_queue.get()

                        if data == SHUTDOWN_CMD:
                            #inputs = []
                            #self.ssl_con.close()
                            #self.rx_queue.put(SHUTDOWN_CMD)
                            self.logger2.info('Shutting down connection monitoring')
                            self.__del__()
                            return None

                        self.__send_data(data)


                for s in exceptional:
                    self.logger2.exception('Select returned an exceptional event')

            except:
                self.logger2.exception('Exception at select.select')
                break

        self.logger2.critical('Connection monitoring ended unexpectedly')


    def __init__(self, s_address, token, send_q, receive_q, log):

        """Setup socket monitoring"""

        self.server_address = s_address
        self.token = token
        self.tx_queue = send_q
        self.rx_queue = receive_q
        self.logger2 = log

        self.ssl_con = None

        self.monitor_socket = threading.Thread(name='monitor_ssl_socket',
                                               target=self.__monitor_socket)
        self.monitor_socket.start()


    def __del__(self):
        self.logger2.info('Deconstructing ACCommunications')
        self.ssl_con.close()
        self.tx_queue.put(self.rx_queue.put(SHUTDOWN_CMD))







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
        return XML_HEADER + ET.tostring(root)


    def __parse_xml_input(self, xml_string):

        """parse xml responses from A/C to a list of dicts"""

        try:

            root = ET.fromstring(xml_string)

            if root.attrib['Type'] == AC_AUTH_TOKEN:
                return [{'ID': AC_AUTH_TOKEN, 'Value': root.attrib['Status']}]

            else:

                func, value, all_attributes = None, None, []

                for node in root.iter():

                    for n in node.keys():

                        if n == 'ID':
                            func = node.get(n)
                        elif n == 'Value':
                            value = node.get(n)

                    if func in VALID_OPERATIONS.keys():
                        all_attributes.append({'ID': func, 'Value': value})

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
            self.logger1.exception('Error updating current status dict, no key:', attribute)
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

                    if type(parsed) is list:
                        for attrib in parsed:
                            self.__update_status_contatiner(attrib['ID'], attrib['Value'])

                        #received full status update
                        if len(parsed) > 1:
                            r_event.set()

            except TypeError:
                break
            except:
                self.logger1.exception('Exception:')

        self.logger1.info('Monitoring of receive queue ended unexpectedly')



    def __poll_status(self):

        """Request A/C status at a regular interval"""

        if self.tx_queue:
            self.tx_queue.put(self.__create_status_request())
        else:
            self.logger1.info('Stopping poll_status thread')
            return None

        polling_thread = None
        polling_thread = threading.Timer(STATUS_POLL_FREQ, self.__poll_status)
        polling_thread.setName('status_polling_thread')
        polling_thread.start()



    def __init__(self):

        config = get_config.get_config(CONFIG_FILE_NAME)

        log_filename = config.get('interface', 'logfile')
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
        self.__poll_status()



    def __del__(self):
        self.logger1.info('Shutting down all everything!')
        self.tx_queue.put(SHUTDOWN_CMD)
        self.rx_queue.put(SHUTDOWN_CMD)
        sleep(2)
        self.tx_queue = None
        self.rx_queue = None
        self.logger1.info('Shutdown of all everything complete, goodbye :)')


    def kill(self):
        self.__del__()

    def shutdown(self):
        self.__del__()


    def __translate(self, status_dict):

        for key in status_dict.keys():
            status_dict[TRANSLATE[key]] = status_dict.pop(key)

        return status_dict


    def get_all_settings(self):
        self.logger1.debug('Requesting A/C current status')
        self.receive_event.clear()
        self.tx_queue.put(self.__create_status_request())

        #Wait for response
        self.receive_event.wait(5)

        if self.receive_event.isSet():
            self.logger1.debug('Received data from A/C')
        else:
            self.logger1.info('No data received, returning cached data')

        return self.__translate(self.status)

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
        val = val.capitalize()
        if val in possible_vals:
            if type(val) is int: val = str(val)
            self.__update_status_contatiner(function, val)
            self.tx_queue.put(self.__create_control_request(function, val))
            return True
        return False

    def set_power(self, val):
        self.__set(AC_POWER, val, VALID_OPERATIONS[AC_POWER])

    def set_mode(self, val):
        if val == 'FAN': val = 'Wind'
        self.__set(AC_MODE, val, VALID_OPERATIONS[AC_MODE])

    def set_fan(self, val):
        self.__set(AC_FAN, val, VALID_OPERATIONS[AC_FAN])

    def set_temp(self, val):
        self.__set(AC_TEMP, int(val), VALID_OPERATIONS[AC_TEMP])

    def set_power_on(self):
        return self.set_power('On')

    def set_power_off(self):
        return self.set_power('Off')