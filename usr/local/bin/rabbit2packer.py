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
    OS_AUTH_FILE = configparser.get('rabbit2packer','OS_AUTH_FILE')
    QUEUE = configparser.get('global','QUEUE')
    QUEUE_HOST = configparser.get('global','QUEUE_HOST')
except Exception as e:
    syslog(LOG_ERR, 'Error reading config file')
    syslog(LOG_ERR, repr(e))
    sys.exit(1)


exitFlag = 0

class imageBuilder:
    def __init__(self, profile_object):
        self.personality = profile_object["system"]["personality"]["name"]
        self.os = profile_object["system"]["aii"]["nbp"]["pxelinux"]["kernel"].split('/')[0]
    def name(self):
        return "%s-%s" % (self.personality, self.os)
    def metadata(self):
        self.metadata = '"AQ_PERSONALITY": "%s"\n' % self.personality
        #self.metadata += '"AQ_OS": "%s"\n' % self.os
        return self.metadata

class workerThread (threading.Thread):
    def __init__(self, name): #threadID, name):
        threading.Thread.__init__(self)
        #self.threadID = threadID
        self.name = name
    def run(self):
        syslog(LOG_INFO, "Starting " + self.name)
        connection = pika.BlockingConnection(pika.ConnectionParameters(host=QUEUE_HOST))
        channel = connection.channel()
        channel.queue_declare(
            queue=QUEUE, 
            durable=True
        )

        worker_loop(self.name, channel)
        syslog(LOG_ERR, "Exiting " + self.name)


def worker_loop(threadName, channel):
    while not exitFlag:
        method_frame, header_frame, body = channel.basic_get(QUEUE)
        if method_frame:
            #syslog(LOG_ERR, method_frame, header_frame, body)
            channel.basic_ack(method_frame.delivery_tag)
            try:
                profile_object = json.loads(body.decode())
                image = imageBuilder(profile_object)
            except ValueError as e:
                syslog(LOG_ERR, repr(e))
                syslog(LOG_ERR, threadName + ": could not decode profile, malformed json? Continuing")
                continue
            except KeyError as e:
                syslog(LOG_ERR, repr(e))
                syslog(LOG_ERR, threadName + ": profile did not contain expected data stucture, malformed json? Continuing")
                continue
            syslog(LOG_ERR, "%s processing %s" % (threadName, image.name()))
            if (run_packer_subprocess(image) != 0):
                syslog(LOG_ERR, threadName + ": packer exited with non zero exit code, build failed")
            else:
                syslog(LOG_INFO, threadName + ": image built succesfully")
            
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

    template = template.replace("$METADATA", image.metadata())
    template = template.replace("$NAME", image_name)

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

    try:
        buildLog = open( log_file_path, "wt")
    except IOError as e:
        syslog(LOG_ERR, "Unable to write to build log file: %s" %  log_file_path )
        syslog(LOG_ERR, repr(e))        
    
    packerCmd = ( "source {auth};"
                  "export OS_TENANT_ID=$OS_PROJECT_ID;"
                  "export OS_DOMAIN_NAME=$OS_USER_DOMAIN_NAME;"  
                  "packer.io build {build_file}"
                ).format(
                    auth=OS_AUTH_FILE, 
                    build_file=build_file_path
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


#exitFlag = 1

# Wait for all threads to complete
#for t in threads:
#    t.join()
#syslog(LOG_ERR, "Exiting Main Thread")

while True:
    time.sleep(5)







