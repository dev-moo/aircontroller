#!/usr/bin/env python

"""
Process config file
"""

import ConfigParser
import os

def get_config(config_file_name):

    """
    Look in directory this script is running for
    a config file and parse it

    Args:
    Name of config file

    Returns:
    Config object
    """

    config = ConfigParser.ConfigParser()

    # Check config file exists and can be accessed, then open
    try:

        this_dir = os.path.dirname(os.path.abspath(__file__))
        filepath = this_dir + '/' + config_file_name

        print filepath

        if not os.path.isfile(filepath):
            print "Error - Missing Config File: %s" % (config_file_name)
            raise IOError('Config file does not exist')

        config.read(filepath)

    except IOError:
        print "Error - Unable to access config file: %s" % (config_file_name)
        exit()

    return config
