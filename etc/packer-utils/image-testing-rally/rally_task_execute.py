#!/usr/bin/env python3
from configparser import SafeConfigParser
from syslog import syslog, LOG_ERR, LOG_INFO
import sys
from subprocess import Popen, STDOUT
from time import time, sleep
import os.path
import json

# Extract config
configparser = SafeConfigParser()
try:
    configparser.read('/etc/packer-utils/config.ini')
    RALLY_DEPLOYMENT_UUID = configparser.get('rally-image-testing', 'DEPLOYMENT_UUID')
    RALLY_CODE_FOLDER = configparser.get('rally-image-testing', 'RALLY_CODE_FOLDER')
    RALLY_TASK_LOCATION = configparser.get('rally-image-testing', 'TASK_LOCATION')
    RALLY_LOG_FOLDER = configparser.get('rally-image-testing', 'LOG_DIR')
    TASK_UUID_EXTRACTION = configparser.get('rally-image-testing', 'TASK_UUID_EXTRACTION')
    UUID_FILE = configparser.get('rally-image-testing', 'UUID_FILE')
except Exception as e:
    syslog(LOG_ERR, 'Unable to read from config file')
    syslog(LOG_ERR, repr(e))
    sys.exit(1)

class RallyTaskExecution:
    def execute_rally_task(self, build_file_path):
        syslog(LOG_INFO, 'Setting up path of log file to get image name')

        # Temp. hardcode until I write some 'proper' Rally tests
        task = 'boot-and-delete.json'
        log_file_path = RALLY_LOG_FOLDER + '/' + task + '-' + repr(int(time())) + '.log'

        task_args = self.form_task_args(build_file_path)

        try:
            # Open log file to be used by Subprocess
            task_log_file = open(log_file_path, "wt")
        except IOError as e:
            syslog(LOG_ERR, "Unable to write to Rally task log file: %s" %  log_file_path )
            syslog(LOG_ERR, repr(e))
            sys.exit(1)

        try:
            syslog(LOG_INFO, 'Launched Rally task, log file for task tracking: {}'.format(log_file_path))
            rally_process = Popen(['{}/execute-image-test.sh'.format(RALLY_CODE_FOLDER),
                                   RALLY_DEPLOYMENT_UUID, '{}/{}'.format(RALLY_TASK_LOCATION, task),
                                   log_file_path, TASK_UUID_EXTRACTION, task_args],
                                   stdout=task_log_file, stderr=STDOUT)

            # Wait until task complete
            rally_process.communicate()
            rally_process.wait()
            syslog(LOG_INFO, 'Rally task finished, about to get UUID')
        except Exception as e:
            syslog(LOG_ERR, 'Error occurred with launching Subprocess to start Rally task:')
            syslog(LOG_ERR, repr(e))
            sys.exit(1)

        # While current_task_uuid.txt doesn't exist, sleep for 3 seconds
        file_checker_clock = 0
        try:
            while(os.path.isfile(UUID_FILE) is False):
                file_checker_clock += 1
                sleep(3)
        except file_checker_clock == 10:
            # Subprocess waits until Rally task has completed, so this timeout is purely on finding UUID
            syslog(LOG_ERR, 'Timeout error to find UUID of Rally task')


    def get_image_name(self, build_file_path):
        syslog(LOG_INFO, 'Inside get_image_name()')

        with open( build_file_path, "r") as build_file:
            data = json.load(build_file)
            try:
                image_name = data['builders'][0]['image_name']
            except TypeError as e:
                syslog(LOG_ERR, 'Cannot find image name inside Packer build file')
                sys.exit(1)

        return image_name


    def form_task_args(self, build_file_path):
        image_name = self.get_image_name(build_file_path)

        # Form json for Rally task args
        task_args = {}
        task_args['image_name'] = image_name
        json_task_args = json.dumps(task_args)

        return json_task_args




# Bash script to execute Rally test on the newly produced image

# Do some testing - get the Rally tests to output the results into json

# Decide if the image is good enough
# Get the json file path and convert it into Python
# Analyse how many tests have passed/failed - need a threshold rate to mark an image to be 'of quality'

# If it's fine, just log that
# If not, delete the image in OpenStack - likely this'll need to be done via Bash
# Function which opens Subprocess to execute a script - it needs the UUID/name of the image passed
