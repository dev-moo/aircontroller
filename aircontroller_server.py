#!/usr/bin/python3

"""Air Con Server"""

import os
import socketserver
import json
import sys
#import socket

THIS_DIR = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, THIS_DIR)

import aircon_interface as AIRCON
import log_handler
import get_config

#HOSTNAME = socket.gethostname()    
#IPADDR = socket.gethostbyname(HOSTNAME)

"""
Sleep timer
"""


class JSONtoACInterface(object):

    """Parse JSON input to AC commands"""

    def __init__(self, log):
        self.logger = log

        #Instantiate AC Interface
        self.aircon = AIRCON.AirConInterface()


    def __del__(self):
        self.logger.info('Shutting down JSONtoACInterface')
        self.aircon.shutdown()

    def shutdown(self):
        self.__del__()


    def __get_settings(self, cmd):

        self.logger.debug('Getting A/C status')

        all_settings = self.aircon.get_all_settings()

        self.logger.debug('Received settings')

        if 'ID' in cmd:
            all_settings['ID'] = cmd['ID']

        return all_settings


    def __set_settings(self, settings):

        """Control A/C"""

        try:

            if 'TIMER' in settings:
                pass
                #start timer thread with 'TIMER' value as sleep time and settings as arg

            if not 'TYPE' in settings:

                #Combine multiple operations into one JSON command

                if 'POWER' in settings:
                    self.aircon.set_power(settings['POWER'])
                if 'MODE' in settings:
                    self.aircon.set_mode(settings['MODE'])
                if 'FAN' in settings:
                    self.aircon.set_fan(settings['FAN'])
                if 'TEMP' in settings:
                    self.aircon.set_temp(settings['TEMP'])

            else:

                #Backwards compatibility - single command per JSON string

                op_type = str(settings['TYPE'])
                val = str(settings['VALUE'])

                if op_type == 'POWER':
                    self.aircon.set_power(val)
                elif op_type == 'MODE':
                    self.aircon.set_mode(val)
                elif op_type == 'FAN':
                    self.aircon.set_fan(val)
                elif op_type == 'TEMP':
                    self.aircon.set_temp(val)

        except KeyError:
            self.logger.exception('Key error when parsing %s', settings)
            if 'ID' in settings:
                return {'RESPONSE': 'FAIL', 'ID': settings['ID']}
            return {'RESPONSE': 'FAIL'}

        if 'ID' in settings:
            return {'RESPONSE': 'OK', 'ID': settings['ID']}
        return {'RESPONSE': 'OK'}



    def parse(self, command):
        """Handle Set and Get operations"""

        self.logger.debug('Received: %s', command)

        try:
            if 'OPERATION' in command:

                if command['OPERATION'] == "GET":
                    if command['TYPE'] == 'SETTINGS':
                        return json.dumps(self.__get_settings(command))

                elif command['OPERATION'] == "SET":
                    #self.__set_settings(command)
                    #return json.dumps({'RESPONSE': 'OK'})
                    #return json.dumps(self.__get_settings())
                    return json.dumps(self.__set_settings(command))

            else:
                self.logger.info('Command contains no Operation')

        except KeyError:
            self.logger.exception('Key error when parsing %s', command)

        return json.dumps(command)




class UDPHandler(socketserver.BaseRequestHandler):
    """
    UDPHandler to handle UDP requests
    """

    def __init__(self, request, client_address, srvr):
        self.logger = LOGGER1
        socketserver.BaseRequestHandler.__init__(self, request, client_address, srvr)
        return

    def handle(self):
        data = self.request[0].strip().upper()
        socket = self.request[1]
        data = data.decode()

        self.logger.debug("From %s: %s", self.client_address[0], data)

        try:
            response = AIRCON_HANDLER.parse(json.loads(data))
            socket.sendto(response.encode(), self.client_address)
        except ValueError:
            self.logger.exception('Exception decoding JSON')



if __name__ == "__main__":

    CONFIG_FILE_NAME = 'aircontroller_config.txt'

    CONFIG = get_config.get_config(CONFIG_FILE_NAME)

    LOG_FILENAME = THIS_DIR + '/' + CONFIG.get('server', 'logfile')
    HOST = CONFIG.get('server', 'server_ip')
    PORT = int(CONFIG.get('server', 'server_port'))

    LOGGER1 = log_handler.get_log_handler(LOG_FILENAME, 'info', 'aircontroller.UDPHandler')
    #LOGGER1 = log_handler.get_log_handler(LOG_FILENAME, 'debug', 'aircontroller.UDPHandler')

    AIRCON_HANDLER = JSONtoACInterface(log_handler.get_log_handler(LOG_FILENAME,
                                                                   'info',
                                                                   'aircontroller.JSONtoAC'))

    LOGGER1.info('Starting UPD server at %s:%d', HOST, PORT)
    SERVER = socketserver.UDPServer((HOST, PORT), UDPHandler)
    
    #LOGGER1.info('Starting UPD server at %s:%d', IPADDR, PORT)
    #SERVER = socketserver.UDPServer((IPADDR, PORT), UDPHandler)
    
    SERVER.allow_reuse_address = True

    try:
        SERVER.serve_forever()
    except (KeyboardInterrupt, SystemExit):
        AIRCON_HANDLER.shutdown()
        SERVER.shutdown()
        SERVER.server_close()
        raise

    LOGGER1.info('UDP SocketServer has shutdown')
