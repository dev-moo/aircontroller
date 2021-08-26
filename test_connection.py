


import sys
import os
import socket
import OpenSSL
import struct


SERVER_IP = '192.168.1.15'
SERVER_PORT = 2878


def get_ssl_connection():

        """Get SSL connection to A/C unit"""
        
        ssl_con = None

        # Prefer TLS
        context = OpenSSL.SSL.Context(OpenSSL.SSL.TLSv1_METHOD)
        context.set_cipher_list('RC4')
        sock = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        #sock.settimeout(5)
        connection = OpenSSL.SSL.Connection(context, sock)
        
        try:
            connection.connect((SERVER_IP, SERVER_PORT))
        except Exception as e:
            print('Unable to connect to A/C: %s %s', e.message, e.args)
            ssl_con = None
            del sock
            del connection
            return False

        # Put the socket in blocking mode
        connection.setblocking(1)

        # Set the timeout using the setsockopt
        connection.setsockopt(socket.SOL_SOCKET,
                              socket.SO_RCVTIMEO,
                              struct.pack('ii', int(6), int(0)))

        print('Connected to %s', connection.getpeername())
        #print('State %s', connection.state_string())
        
        try:
            connection.do_handshake()
        #except OpenSSL.SSL.WantReadError:
        except Exception as e:
            print('Handshake failed %s', connection.state_string())
            connection.close()
            ssl_con = None
            del sock
            del connection
            return False
            
        print(connection.get_cipher_list())
        print('----------')
        print(connection.get_client_ca_list())
        print('----------')
        #print(connection.get_cipher_bits())
        #print('----------')
        print('State %s', connection.state_string())
        
        
        data = connection.recv(1024)
        print(data)
        data = connection.recv(1024)
        print(data)
        #self.tx_queue.put(self.__create_authentication_request())

        return ssl_con


get_ssl_connection()

