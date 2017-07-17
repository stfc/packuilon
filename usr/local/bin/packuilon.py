#!/usr/bin/env python3
# this script generates and pushes a skeleton profile to the image factory message queue
# triggering a build of that particular personality

import sys
import pika
import argparse
import json
from configparser import SafeConfigParser

def pushMessageToQueue(message):
    try: 
        channel.basic_publish(exchange='',
                              routing_key=QUEUE,
                              body=message,
                              properties=pika.BasicProperties(
                                  delivery_mode=2,
                              ))
    except Exception as e:
        print('Unable to push message to queue, exiting without updating cached profile_info')
        print(repr(e))

# read config
configparser = SafeConfigParser()
try:
    configparser.read('/etc/packer-utils/config.ini')
    PROFILE_DIR_URL = configparser.get('cdb2rabbit','PROFILE_DIR_URL')
    QUEUE = configparser.get('global','QUEUE')
    RABBIT_HOST = configparser.get('global','RABBIT_HOST')
    RABBIT_PORT = configparser.getint('global','RABBIT_PORT')
    RABBIT_USER = configparser.get('global','RABBIT_USER')
    RABBIT_PW = configparser.get('global','RABBIT_PW')
except Exception as e:
    print('Unable to read from config file')
    print(repr(e))
    sys.exit(1)

# set up command line args
parser = argparse.ArgumentParser(description='Build an Glance image based on a aquilon profile by specifying the personailty, domain/sandbox, archetype and OS.')

parser.add_argument('--personality', help='Personality of profile')
parser.add_argument('--archetype', default='ral-tier1', help='Archetype of profile')
parser.add_argument('--os', default='sl', help='OS of profile e.g. "sl"')
parser.add_argument('--os_ver', default='7x', help='OS version of profile e.g. "7x"')
parser.add_argument('--arch', default='x86_64', help='OS of profile e.g. "sl"')

# user can specify domain or sandbox, but not both
domainSandbox = parser.add_mutually_exclusive_group()
domainSandbox.add_argument('--domain', default='prod', help='Domain of profile, cannot be used with --sandbox')
domainSandbox.add_argument('--sandbox', help='Sandbox of profile, cannot be used with --domain. Use the form "owner/sandbox"')

# parse them!
args = parser.parse_args()

# start creating the profile 
# need a bit of logic for the different structures of the sandbox/domain
if args.sandbox:
    author,sandbox=args.sandbox.split("/")
    branch = { "author" : author, "name" : sandbox, "type" : "sandbox" }
else:
    branch = { "name" : args.domain, "type" : "domain" }

# fill the object
profile_object = { 
    "metadata" : {
        "template" : { "branch" : branch }
    }, 
    "system" : {  
        "personality" : { "name" :  args.personality }, 
        "archetype" : { "name" : args.archetype}, 
        "os" : {
            "architecture" : args.arch,
            "distribution" : { "name" : args.os },
            "version" : { "name" : args.os_ver }
        } 
    } 
} 

print(profile_object)

# open connection to RabbitMQ host
try:
    credentials = pika.PlainCredentials(RABBIT_USER,RABBIT_PW)
    parameters = pika.ConnectionParameters(RABBIT_HOST,
                                       RABBIT_PORT,
                                       "/",
                                       credentials,
                                       connection_attempts=10,
                                       retry_delay=2)
    connection = pika.BlockingConnection(parameters)
    channel = connection.channel()
    channel.queue_declare(queue=QUEUE, durable=True)
except (pika.exceptions.AMQPError, pika.exceptions.ChannelError) as e:
    print('Error connecting to RabbitMQ server:')
    print(repr(e))
    sys.exit(1)

# push the object to the queue
pushMessageToQueue(json.dumps(profile_object))

sys.exit(0)
