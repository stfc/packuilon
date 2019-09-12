#!/usr/bin/env python3
from configparser import SafeConfigParser
from syslog import syslog, LOG_ERR, LOG_INFO
import sys
from subprocess import Popen, STDOUT
from time import time

# Extract config
configparser = SafeConfigParser()
try:
    configparser.read('/etc/packer-utils/config.ini')
    RALLY_DEPLOYMENT_UUID = configparser.get('rally-image-testing', 'DEPLOYMENT_UUID')
    RALLY_CODE_FOLDER = configparser.get('rally-image-testing', 'RALLY_CODE_FOLDER')
    RALLY_TASK_LOCATION = configparser.get('rally-image-testing', 'TASK_LOCATION')
    RALLY_LOG_FOLDER = configparser.get('rally-image-testing', 'LOG_DIR')
except Exception as e:
    syslog(LOG_ERR, 'Unable to read from config file')
    syslog(LOG_ERR, repr(e))
    sys.exit(1)


def execute_rally_task():
    # Temp. hardcode until I write some 'proper' Rally tests
    task = 'boot-and-delete.json'

    log_file_path = RALLY_LOG_FOLDER + '/' + task + '-' + repr(int(time())) + '.log'

    try:
            task_log_file = open( log_file_path, "wt")
    except IOError as e:
        syslog(LOG_ERR, "Unable to write to Rally task log file: %s" %  log_file_path )
        syslog(LOG_ERR, repr(e))
        sys.exit(1)

    Popen(['{}/execute-image-test.sh'.format(RALLY_CODE_FOLDER), RALLY_DEPLOYMENT_UUID, '{}/{}'.format(RALLY_TASK_LOCATION, task)], stdout=task_log_file, stderr=STDOUT)
    syslog(LOG_INFO, 'Launched Rally task')

# Execute Rally task
execute_rally_task()



# Bash script to execute Rally test on the newly produced image

# Do some testing - get the Rally tests to output the results into json

# Decide if the image is good enough
# Get the json file path and convert it into Python
# Analyse how many tests have passed/failed - need a threshold rate to mark an image to be 'of quality'

# If it's fine, just log that
# If not, delete the image in OpenStack - likely this'll need to be done via Bash
# Function which opens Subprocess to execute a script - it needs the UUID/name of the image passed
