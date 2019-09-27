#!/usr/bin/env python3
import sys
sys.path.append("/etc/packer-utils/image-testing-rally/")
from rally_task_execute import RallyTaskExecution
from rally_task_analysis import RallyTaskAnalysis
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
    PACKER_TEMPLATE_MAP = configparser.get('rabbit2packer','PACKER_TEMPLATE_MAP')
    LOG_DIR = configparser.get('rabbit2packer','LOG_DIR')
    BUILD_FILE_DIR = configparser.get('rabbit2packer','BUILD_FILE_DIR')
    PACKER_AUTH_FILE = configparser.get('rabbit2packer','PACKER_AUTH_FILE')
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

try:
    with open(PACKER_TEMPLATE_MAP) as template_map_JSON:
        TEMPLATE_MAP = json.load(template_map_JSON)
except IOError as e:
    syslog(LOG_ERR, repr(e))
    syslog(LOG_ERR, "Could not open template map file.")
    sys.exit(1)
except ValueError as e:
    syslog(LOG_ERR, repr(e))
    syslog(LOG_ERR, "Could not decode template map file, malformed json?")
    sys.exit(1)



exitFlag = 0

class imageBuilder:
    def __init__(self, profile_object):
        self.personality = profile_object["system"]["personality"]["name"]
        if not (self.personality):
            raise KeyError('personality value not found in profile, cannot continue build')
        self.archetype = profile_object["system"]["archetype"]["name"]
        if not (self.archetype):
            raise KeyError('archetype value not found in profile, cannot continue build')
        self.architecture = profile_object["system"]["os"]["architecture"]
        if not (self.architecture):
            raise KeyError(' architecture value not found in profile, cannot continue build')
        self.os = profile_object["system"]["os"]["distribution"]["name"]
        if not (self.os):
            raise KeyError('OS value not found in profile, cannot continue build')
        self.os_ver = profile_object["system"]["os"]["version"]["name"]
        if not (self.personality):
            raise KeyError('os_ver value not found in profile, cannot continue build')
        self.imageID = IMAGES["%s%s-%s" % (self.os, self.os_ver, self.architecture)]
        if not (self.imageID):
            raise KeyError('source image not found in dict for key %s%s-%s' % self.os, self.os_ver, self.architecture)
        syslog(LOG_INFO, 'Personality: {}, Archetype: {}, OS: {}, OS Version: {}'.format(self.personality, self.archetype, self.os, self.os_ver))
    def name(self):
        return "%s-%s%s-%s" % (self.personality, self.os, self.os_ver, self.architecture)
    def prettyName(self):
        return "%s%s-%s %s" % (self.os, self.os_ver, self.architecture, self.personality)
    def imageID(self):
        return self.imageID
    def metadata(self):
        self.metadata = '"AQ_PERSONALITY": "%s", ' % self.personality
        self.metadata += '"AQ_OS": "%s", ' % self.os
        self.metadata += '"AQ_OSVERSION": "%s-%s", ' % (self.os_ver, self.architecture)
        self.metadata += '"AQ_DOMAIN": "prod", '
        self.metadata += '"AQ_ARCHETYPE": "%s"' % (self.archetype)
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
                syslog(LOG_ERR, threadName + ": source image was not found, check IMAGES_CONFIG. Continuing")
                continue
            syslog(LOG_ERR, "%s processing %s" % (threadName, image.name()))
            run_packer_subprocess(threadName, image)

        time.sleep(2)


def run_packer_subprocess(threadName, image):

    image_name=image.name()
    image_display_name=image.prettyName()
    image_metadata=image.metadata()

    try:
        source_image_ID = image.imageID
    except KeyError as e:
        syslog(LOG_ERR, "Source image for " + image_name + " not defined in " + IMAGES_CONFIG + ". Skipping build")
        syslog(LOG_ERR, "Check for relevant OS entry in " + IMAGES_CONFIG)
        return

    templates = TEMPLATE_MAP.get(image_name)

    if templates is None:
        templates = TEMPLATE_MAP.get("DEFAULT")
        syslog(LOG_INFO, "No Packer template defined for " + image_name + ". Using the default values")

    if templates is None:
        syslog(LOG_INFO, "No Packer template defined for Default values. No builds will occur.")

    for template in templates:
        template_name=template.rsplit('/', 1)[-1]
        try:
            with open( template, "rt") as template_file:
                template = template_file.read()
        except FileNotFoundError as e:
            syslog(LOG_ERR, "Could not find packer template file, exiting")
            syslog(LOG_ERR, repr(e))
            sys.exit(1)
        except IOError as e:
            syslog(LOG_ERR, "Unable to open template file")
            syslog(LOG_ERR, repr(e))
            sys.exit(1)

        template = template.replace("$METADATA", image_metadata)
        template = template.replace("$NAME", image_display_name)
        template = template.replace("$IMAGE", source_image_ID)

        build_file_path=BUILD_FILE_DIR + '/' + image_name + "." + template_name + ".json"
        build_start_time = int(time.time())
        log_file_path=LOG_DIR + '/' + image_name + "." + template_name + "." + repr(build_start_time) + ".log"

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
                      "packer.io build {build_file};"
                    ).format(
                        packer_auth=PACKER_AUTH_FILE,
                        build_file=build_file_path
                    )

        syslog(LOG_INFO, "packer build starting, see: " + log_file_path + " for details")

        packerProc = subprocess.Popen(packerCmd, shell=True, stdout=buildLog, stderr=subprocess.STDOUT)
        ret_code = packerProc.wait()
        build_finish_time = int(time.time())
        buildLog.write("rabbit2packer: Build finished at %s (epoch) with exit code %s\n" % (build_finish_time, ret_code))
        if (ret_code != 0):
            syslog(LOG_ERR, threadName + ": packer exited with non zero exit code, " + image_name + "." + template_name+ " build failed")
        else:
            syslog(LOG_INFO, threadName + ": image built successfully: " + image_name + "." + template_name)
            RallyTaskExecution().execute_rally_task(build_file_path)
            RallyTaskAnalysis().test_analysis()

threads = []

# Create new threads
for i in range(THREAD_COUNT):
    thread = workerThread("Thread-" + str(i + 1))
    thread.start()
    threads.append(thread)

while True:
    time.sleep(5)
