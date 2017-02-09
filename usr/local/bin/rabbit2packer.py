#!/usr/bin/env python3
import sys
import pika
from syslog import syslog, LOG_ERR, LOG_INFO
from configparser import SafeConfigParser
import subprocess  
import threading
import time
import json

syslog(LOG_INFO, 'Starting')


# Config
configparser = SafeConfigParser()
try:
    configparser.read('/etc/packer-utils/config.ini')
    THREAD_COUNT = configparser.getint('rabbit2packer','THREAD_COUNT')
    if (THREAD_COUNT < 1):
        raise UserWarning('A thread count < 1 is defined, no worker threads will run')
    PACKER_TEMPLATE = configparser.get('rabbit2packer','PACKER_TEMPLATE')
    LOG_DIR = configparser.get('rabbit2packer','LOG_DIR')
    BUILD_FILE_DIR = configparser.get('rabbit2packer','BUILD_FILE_DIR')
    PACKER_AUTH_FILE = configparser.get('rabbit2packer','PACKER_AUTH_FILE')
    ADMIN_AUTH_FILE = configparser.get('rabbit2packer','ADMIN_AUTH_FILE')
    QUEUE = configparser.get('global','QUEUE')
    IMAGES_CONFIG = configparser.get('rabbit2packer','IMAGES_CONFIG')
    RABBIT_HOST = configparser.get('global','RABBIT_HOST')
    RABBIT_PORT = configparser.getint('global','RABBIT_PORT')
    RABBIT_USER = configparser.get('global','RABBIT_USER')
    RABBIT_PW = configparser.get('global','RABBIT_PW')
except Exception as e:
    syslog(LOG_ERR, 'Error reading config file')
    syslog(LOG_ERR, repr(e))
    sys.exit(1)

try:
    with open(IMAGES_CONFIG) as images_JSON:    
        IMAGES = json.load(images_JSON)
except IOError as e:
    syslog(LOG_ERR, repr(e))
    syslog(LOG_ERR, "Could not open images config file.")
    sys.exit(1)
except ValueError as e:
    syslog(LOG_ERR, repr(e))
    syslog(LOG_ERR, "Could not decode images config file, malformed json?")
    sys.exit(1)



exitFlag = 0

class imageBuilder:
    def __init__(self, profile_object):
        self.personality = profile_object["system"]["personality"]["name"]
        self.os_string = profile_object["system"]["aii"]["nbp"]["pxelinux"]["kernel"].split('/')[0]
        self.os = ""
        self.os_ver = ""
        for os in IMAGES:
            if self.os_string.startswith(os):
                for ver in IMAGES[os]:
                    if self.os_string == os + ver:
                        self.os = os
                        self.os_ver = ver
                        self.imageID = IMAGES[self.os][self.os_ver]
        if not (self.os and self.os_ver):
            raise KeyError('os and os_ver not found in the source image dict')
    def name(self):
        return "%s-%s" % (self.personality, self.os_string)
    def imageID(self):
        return self.imageID
    def metadata(self):
        self.metadata = '"AQ_PERSONALITY": "%s",\n' % self.personality
        self.metadata += '"AQ_OS": "%s",\n' % self.os
        self.metadata += '"AQ_OSVERSION": "%s"\n' % self.os_ver
        return self.metadata

class workerThread (threading.Thread):
    def __init__(self, name):
        threading.Thread.__init__(self)

        self.name = name
    def run(self):
        syslog(LOG_INFO, "Starting " + self.name)
        credentials = pika.PlainCredentials(RABBIT_USER,RABBIT_PW)
        parameters = pika.ConnectionParameters(RABBIT_HOST,
                                       RABBIT_PORT,
                                       "/",
                                       credentials,
                                       connection_attempts=10,
                                       retry_delay=2)
        connection = pika.BlockingConnection(parameters)

        channel = connection.channel()
        channel.queue_declare(
            queue=QUEUE, 
            durable=True
        )

        worker_loop(self.name, channel)
        syslog(LOG_ERR, "Exiting " + self.name)


def worker_loop(threadName, channel):
    while not exitFlag:
        try:
            method_frame, header_frame, body = channel.basic_get(QUEUE)
        except pika.exceptions.ConnectionClosed as e:
            credentials = pika.PlainCredentials(RABBIT_USER,RABBIT_PW)
            parameters = pika.ConnectionParameters(RABBIT_HOST,
                                           RABBIT_PORT,
                                           "/",
                                           credentials,
                                           connection_attempts=10,
                                           retry_delay=2)
            connection = pika.BlockingConnection(parameters)

            channel = connection.channel()
            channel.queue_declare(
                queue=QUEUE,
                durable=True
            )
            syslog(LOG_INFO, threadName + ": reconnecting to channel")
            continue

        if method_frame:
            channel.basic_ack(method_frame.delivery_tag)
            try:
                profile_object = json.loads(body.decode())
            except ValueError as e:
                syslog(LOG_ERR, repr(e))
                syslog(LOG_ERR, threadName + ": could not decode profile, malformed json? Continuing")
                continue

            try:
                image = imageBuilder(profile_object)
            except KeyError as e:
                syslog(LOG_ERR, repr(e))
                syslog(LOG_ERR, threadName + ": source imge was not found, check IMAGES_CONFIG. Continuing")
                continue
            syslog(LOG_ERR, "%s processing %s" % (threadName, image.name()))
            if (run_packer_subprocess(image) != 0):
                syslog(LOG_ERR, threadName + ": packer exited with non zero exit code, build failed")
            else:
                syslog(LOG_INFO, threadName + ": image built successfully")
            
        time.sleep(2)


def run_packer_subprocess(image):

    image_name=image.name()

    try:
        with open( PACKER_TEMPLATE, "rt") as template_file:
            template = template_file.read()
    except FileNotFoundError:
        syslog(LOG_ERR, "Could not find packer template file, exiting")
        sys.exit(1)
    except IOError as e:
        syslog(LOG_ERR, "Unable to open template file")
        syslog(LOG_ERR, repr(e))
        sys.exit(1)


    try:
        source_image_ID = image.imageID
    except KeyError as e:
        syslog(LOG_ERR, "Source image for " + image_name + " not defined in " + IMAGES_CONFIG + ". Skipping build")
        syslog(LOG_ERR, "Check for relevant OS entry in " + IMAGES_CONFIG)
        return 1

    template = template.replace("$METADATA", image.metadata())
    template = template.replace("$NAME", image_name)
    template = template.replace("$IMAGE", source_image_ID)

    #"AQ_ARCHETYPE": "$ARCHETYPE",
    #                "AQ_DOMAIN": "$DOMAIN",
    #                "AQ_OS": "$OS",
    #                "AQ_OSVERSION": "$OSVERSION",
    #                "AQ_PERSONALITY": "$PERSONALITY",
    #                "AQ_SANDBOX": "$SANDBOX"


    build_file_path=BUILD_FILE_DIR + '/' + image_name + ".json"
    log_file_path=LOG_DIR + '/' + image_name + ".log"

    try:
        with open( build_file_path, "wt") as buildFile:
            buildFile.write(template)
    except IOError as e:
        syslog(LOG_ERR, "Unable to write build file: %s" %  build_file_path )
        syslog(LOG_ERR, repr(e))        
        sys.exit(1)

    try:
        buildLog = open( log_file_path, "wt")
    except IOError as e:
        syslog(LOG_ERR, "Unable to write to build log file: %s" %  log_file_path )
        syslog(LOG_ERR, repr(e))
        sys.exit(1)
    
    packerCmd = ( "source {packer_auth};"
                  "export OS_TENANT_ID=$OS_PROJECT_ID;"
                  "export OS_DOMAIN_NAME=$OS_USER_DOMAIN_NAME;"  
                  "packer.io build {build_file} &&"
                  "source {admin_auth} &&" 
                  "rename-old-images.sh {name}"
                ).format(
                    packer_auth=PACKER_AUTH_FILE, 
                    build_file=build_file_path,
                    name=image_name,
                    admin_auth=ADMIN_AUTH_FILE
                )

    syslog(LOG_INFO, "packer build starting, see: " + log_file_path + " for details")

    packerProc = subprocess.Popen(packerCmd, shell=True, stdout=buildLog, stderr=subprocess.STDOUT)
    ret_code = packerProc.wait()
    return ret_code

threads = []

# Create new threads
for i in range(THREAD_COUNT):
    thread = workerThread("Thread-" + str(i + 1))
    thread.start()
    threads.append(thread)

while True:
    time.sleep(5)







