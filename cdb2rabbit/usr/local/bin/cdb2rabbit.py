#!/usr/bin/env python3
import sys
import pika
import xml.etree.ElementTree as ET
from syslog import syslog, LOG_ERR, LOG_INFO
from urllib.request import urlopen
from urllib.error import URLError, HTTPError
from configparser import SafeConfigParser

# Config
configparser = SafeConfigParser()
try:
    configparser.read('/etc/packer-utils/config.ini')
    PROFILE_INFO_URL = configparser.get('cdb2rabbit','PROFILE_INFO_URL')
    PROFILE_DIR_URL = configparser.get('cdb2rabbit','PROFILE_DIR_URL')
    CACHE_DIR = configparser.get('cdb2rabbit','CACHE_DIR')
    QUEUE = configparser.get('cdb2rabbit','QUEUE')
    QUEUE_HOST = configparser.get('cdb2rabbit','QUEUE_HOST')
except:
    print('Unable to read from config file')
sys.exit(1)


def updateCachedFile(file_name, contents):
    try:
        with open(file_name, "wt") as file:
            file.write(contents)
    except IOError as e:
        syslog(LOG_ERR, "Unable to write profile info to file, check permissions")

def pushMessageToQueue(message):
    try: 
        channel.basic_publish(exchange='',
                              routing_key=QUEUE,
                              body=message,
                              properties=pika.BasicProperties(
                                  delivery_mode=2,
                              ))
    except Exception:
        syslog(LOG_ERR, 'Unable to push message to queue, exiting without updating cached profile_info')
        

def hasProfileUpdated(profile):
    syslog(LOG_INFO, 'Downloading profile ' + profile)
    try:
        with urlopen(PROFILE_DIR_URL + profile) as response:
            new_profile = response.read().decode('utf-8')
    except URLError as e:
        if hasattr(e, 'code'):
            syslog(LOG_ERR, "Error retriving profile: " + profile)
            syslog(LOG_ERR,'Error code: ', e.code)
        elif hasattr(e, 'reason'):
            syslog(LOG_ERR,'We failed to reach a server.')
            syslog(LOG_ERR,'Reason: ', e.reason)
        sys.exit(1)

    try:
        with open(CACHE_DIR + "profiles/" + profile, "rt") as cached_profile_file:
            cached_profile = cached_profile_file.read()
    except FileNotFoundError:
        syslog(LOG_INFO, "cached profile " + profile + " does not exist, creating one and continuing")
        updateCachedFile(CACHE_DIR + "profiles/" + profile, new_profile)
        return False
    except IOError as e:
        syslog(LOG_ERR, "Unable to open cached profile: " + profile)
        syslog(LOG_ERR,e)
        sys.exit(1)
    
    for line in new_profile.splitlines():
        if line not in cached_profile:
            updateCachedFile(CACHE_DIR + "profiles/" + profile, new_profile)
            return True
    return False

# Open connection to RabbitMQ host
try:
    connection = pika.BlockingConnection(pika.ConnectionParameters(QUEUE_HOST))
    channel = connection.channel()
    channel.queue_declare(queue='build-queue', durable=True)
except:
    syslog(LOG_ERR, 'Error connecting to RabbitMQ server')

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
    with open(CACHE_DIR + "cached_info.xml", "rt") as cached_info_file:
        cached_info = cached_info_file.read()
except FileNotFoundError:
    syslog(LOG_INFO, "Cached info file does not exist, creating one and exiting")
    updateCachedFile( CACHE_DIR + "cached_info.xml", new_info)
    sys.exit(0)
except IOError as e:
    syslog(LOG_ERR, "Unable to open cached info file:")
    syslog(LOG_ERR,e)

# Compare the files
for line in new_info.splitlines():
    # If a line is new
    if line not in cached_info:
        profile = ET.fromstring(line).text
        # And is a continuous integration profile
        if ".testing.internal.json" in profile:
            syslog(LOG_INFO, "CI profile rebuilt: " + profile)
            # Check to see if it has changed since we last ran
            if hasProfileUpdated(profile):
                syslog(LOG_INFO, "Profile has updated: " + profile)
                syslog(LOG_INFO, "Pushing message to queue for build")
                # And if so, push a message to the queue
                pushMessageToQueue(profile)
            else:
                syslog(LOG_INFO, "Profile has not updated:" + profile)

# Update the cached info file before exixting
syslog(LOG_INFO, "updating cached profile_info")
updateCachedFile( CACHE_DIR + "cached_info.xml", new_info)
sys.exit(0)
