from configparser import SafeConfigParser
from syslog import syslog, LOG_ERR, LOG_INFO
from subprocess import Popen, STDOUT
import sys
import os
import json

# Extract config
configparser = SafeConfigParser()
try:
    configparser.read('/etc/packer-utils/config.ini')
    UUID_FILE = configparser.get('rally-image-testing', 'UUID_FILE')
    RALLY_JSON_RESULTS = configparser.get('rally-image-testing', 'RALLY_JSON_RESULTS')
except Exception as e:
    syslog(LOG_ERR, 'Unable to read from config file')
    syslog(LOG_ERR, repr(e))
    sys.exit(1)


class RallyTaskAnalysis:
    def test_analysis(self):
        task_uuid = self.get_task_uuid()
        json_results = self.get_json_data(task_uuid)

        image_ok = True
        self.analyse_json_data(json_results)


        # Making results of this data analysis clearer in the logging
        image_results_header = [
            '-----------------------------------------',
            '++++++++ RESULTS OF IMAGES BELOW ++++++++',
            '-----------------------------------------'
        ]
        for line in image_results_header:
            syslog(LOG_INFO, line)
        
        if image_ok is False:
            # Image is broken, needs to be destroyed
            syslog(LOG_INFO, 'Image has failed quality checks and needs to be addressed..')
        else:
            syslog(LOG_INFO, 'Image is of sufficient quality and passed checks.')


    def get_task_uuid(self):
        syslog(LOG_INFO, 'Analysis of test results beginning')
        try:
            with open(UUID_FILE, 'r') as task_uuid_file:
                task_uuid = task_uuid_file.read()
            syslog(LOG_INFO, 'UUID: {}'.format(task_uuid))
        except IOError as e:
            syslog(LOG_ERR, "Unable to open file storing UUID")
            syslog(LOG_ERR, repr(e))
            sys.exit(1)

        # Removing file so timeout in rally_task_execute.py still functions
        os.remove(UUID_FILE)

        return task_uuid


    def get_json_data(self, task_uuid):
        results_file_path = RALLY_JSON_RESULTS + task_uuid + '.json'
        try:
            with open(results_file_path, 'r') as results_file:
                json_results = json.load(results_file)
        except IOError as e:
            syslog(LOG_ERR, 'Unable to retrieve json data from: {}'.format(results_file_path))
            syslog(LOG_ERR, repr(e))
            sys.exit(1)

        return json_results


    def analyse_json_data(self, data):
        ''' 
        Function looks at various sections of the data and points are scored for sections which
        meet criteria set within the function. Set percentage of points must be scored (so not
        everything must succeed, but most), and the task's SLA must also pass to ensure image is
        of sufficient quality
        '''

        self.success_total_points = 0
        self.success_scored_points = 0
        self.success_criteria_pass_percentage = 90

        try:
            for task, task_number in zip(data['tasks'], range(len(data['tasks']))):
                syslog(LOG_INFO, 'UUID of task #{}: {}'.format(task_number, task['uuid']))
                for subtask in task['subtasks']:
                    syslog(LOG_INFO, 'Title of subtask: {}'.format(subtask['title']))
                    for workload in subtask['workloads']:
                        # Nitty gritty results in the workload section of json
                        syslog(LOG_INFO, 'UUID of workload: {}'.format(workload['uuid']))

                        # Does Rally think the test passed or not?
                        rally_pass_sla = workload['pass_sla']

                        # Grabbing percentages from json data
                        self.criteria_percentage_test(workload['statistics']['durations']['total']['data']['success'])
                        for child_duration in workload['statistics']['durations']['total']['children']:
                            self.criteria_percentage_test(child_duration['data']['success'])

                        for atomics in workload['statistics']['durations']['atomics']:
                            self.criteria_percentage_test(atomics['data']['success'])



        except KeyError as e:
            syslog(LOG_ERR, 'Key in JSON data couldn\'t be found')
            syslog(LOG_ERR, repr(e))

        try:
            if (self.success_scored_points / self.success_total_points) * 100 > self.success_criteria_pass_percentage:
                success_criteria = True
            else:
                success_criteria = False
        except ZeroDivisionError as e:
            syslog(LOG_ERR, repr(e))
            syslog(LOG_ERR, 'Divide by zero error, setting success criteria to false')
            # Assigning it to false is better than exiting the program
            success_criteria = False

        syslog(LOG_INFO, 'Scored points: {}, total points: {}, success_criteria: {}'.format(
            self.success_scored_points, self.success_total_points, str(success_criteria)))

        # Determining whether image should pass checks based on Rally's criteria and criteria 
        # tested in this file
        if success_criteria and rally_pass_sla:
            return True
        else:
            return False


    def strip_percentage_sign(self, percentage_string_value):
        '''
        Removing percentage sign from input value to convert from string (as stored in json file)
        to a float to manipulate
        '''

        return float(percentage_string_value.strip('%'))

    
    def criteria_percentage_test(self, percentage_string):
        if float(self.strip_percentage_sign(percentage_string)) > self.success_criteria_pass_percentage:
            self.success_scored_points += 1
            self.success_total_points += 1
