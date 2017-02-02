#!/usr/bin/env python3
import sys
import pika
import xml.etree.ElementTree as ET
from syslog import syslog, LOG_ERR, LOG_INFO
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from configparser import SafeConfigParser

syslog(LOG_INFO, 'Starting')

# Config
configparser = SafeConfigParser()
try:
    configparser.read('/etc/packer-utils/config.ini')
    PROFILE_INFO_URL = configparser.get('cdb2rabbit','PROFILE_INFO_URL')
    PROFILE_DIR_URL = configparser.get('cdb2rabbit','PROFILE_DIR_URL')
    PROFILE_MATCH = configparser.get('cdb2rabbit','PROFILE_MATCH')
    CACHE_DIR = configparser.get('cdb2rabbit','CACHE_DIR')
    QUEUE = configparser.get('global','QUEUE')
    RABBIT_HOST = configparser.get('global','RABBIT_HOST')
    RABBIT_PORT = configparser.getint('global','RABBIT_PORT')
    RABBIT_USER = configparser.get('global','RABBIT_USER')
    RABBIT_PW = configparser.get('global','RABBIT_PW')
except Exception as e:
    syslog(LOG_ERR, 'Unable to read from config file')
    syslog(LOG_ERR, repr(e))
    sys.exit(1)

def updateCachedFile(file_name, contents):
    try:
        with open(file_name, "wt") as file:
            file.write(contents)
    except IOError as e:
        syslog(LOG_ERR, "Unable to write profile info to file %s" % file_name)
        syslog(LOG_ERR, repr(e))

def pushMessageToQueue(message):
    try: 
        channel.basic_publish(exchange='',
                              routing_key=QUEUE,
                              body=message,
                              properties=pika.BasicProperties(
                                  delivery_mode=2,
                              ))
    except Exception as e:
        syslog(LOG_ERR, 'Unable to push message to queue, exiting without updating cached profile_info')
        syslog(LOG_ERR, repr(e))

def downloadProfile(profile):
    syslog(LOG_INFO, 'Downloading profile ' + profile)
    try:
        with urlopen(PROFILE_DIR_URL + "/" + profile) as response:
            profile_contents = response.read().decode('utf-8')
    except URLError as e:
        if hasattr(e, 'code'):
            syslog(LOG_ERR, "Error retriving profile: " + profile)
            syslog(LOG_ERR,'Error code: ', e.code)
        elif hasattr(e, 'reason'):
            syslog(LOG_ERR,'We failed to reach a server.')
            syslog(LOG_ERR,'Reason: ', e.reason)
        sys.exit(1)
  
    return profile_contents


def hasProfileUpdated(profile_name, new_profile_contents):
    try:
        with open(CACHE_DIR + "/" + profile_name, "rt") as cached_profile_file:
            cached_profile = cached_profile_file.read()
    except FileNotFoundError:
        syslog(LOG_INFO, "cached profile " + profile + " does not exist, creating one and continuing")
        updateCachedFile(CACHE_DIR + "/" + profile_name, new_profile_contents)
        return False
    except IOError as e:
        syslog(LOG_ERR, "Unable to open cached profile: " + profile_name)
        syslog(LOG_ERR, repr(e))
        sys.exit(1)
    
    for line in new_profile_contents.splitlines():
        if line not in cached_profile:
            updateCachedFile(CACHE_DIR + "/" + profile_name, new_profile_contents)
            return True
    return False

# Open connection to RabbitMQ host
try:
    credentials = pika.PlainCredentials(RABBIT_USER,RABBIT_PW)
    parameters = pika.ConnectionParameters(RABBIT_HOST,
                                       RABBIT_PORT,
                                       "/",
                                       credentials,
                                       connection_attempts=10,
                                       retry_delay=2)
    connection = pika.BlockingConnection(parameters)

    #connection = pika.BlockingConnection(pika.ConnectionParameters(RABBIT_HOST))
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE, durable=True)
except (pika.exceptions.AMQPError, pika.exceptions.ChannelError) as e:
    syslog(LOG_ERR, 'Error connecting to RabbitMQ server:')
    syslog(LOG_ERR, repr(e))
    sys.exit(1)

# Grab the profile info file
try:
    with urlopen(PROFILE_INFO_URL) as response:
        new_info = response.read().decode('utf-8')
except URLError as e:
    if hasattr(e, 'code'):
        syslog(LOG_ERR,'The server couldn\'t fulfill the request.')
        syslog(LOG_ERR,'Error code: ', e.code)
    elif hasattr(e, 'reason'):
        syslog(LOG_ERR,'We failed to reach a server.')
        syslog(LOG_ERR,'Reason: ', e.reason)
    sys.exit(1)

# Open the cached profile info file
try:
    with open(CACHE_DIR + "/" + "cached_info.xml", "rt") as cached_info_file:
        cached_info = cached_info_file.read()
except FileNotFoundError:
    syslog(LOG_INFO, "Cached info file does not exist, creating one and exiting")
    updateCachedFile( CACHE_DIR + "cached_info.xml", new_info)
    sys.exit(0)
except IOError as e:
    syslog(LOG_ERR, "Unable to open cached info file:")
    syslog(LOG_ERR, repr(e))

# Compare the files
for line in new_info.splitlines():
    # If a line is new
    if line not in cached_info:
        profile = ET.fromstring(line).text
        # And is a profile we are interested in
        if PROFILE_MATCH in profile:
            syslog(LOG_INFO, "CI profile rebuilt: " + profile)
            profile_contents = downloadProfile(profile)
            # Check to see if it has changed since we last ran
            if hasProfileUpdated(profile, profile_contents):
                syslog(LOG_INFO, "Profile has updated: " + profile)
                syslog(LOG_INFO, "Pushing message to queue for build")
                # And if so, push a message containing the profile to the queue
                pushMessageToQueue(profile_contents)
            else:
                syslog(LOG_INFO, "Profile has not updated: " + profile)

# Update the cached info file before exixting
syslog(LOG_INFO, "Updating cached profile_info")
updateCachedFile( CACHE_DIR + "/" + "cached_info.xml", new_info)
syslog(LOG_INFO, "Exiting normally")
sys.exit(0)
