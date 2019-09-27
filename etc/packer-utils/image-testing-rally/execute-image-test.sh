#!/bin/sh

deployment_uuid=$1
task_file=$2
log_file=$3
uuid_extractor_script=$4
# Final argument so it can be optional
task_args=$5

# Deployment explictly set in case of multiple deployments on the machine
rally deployment use $deployment_uuid

if [ -n "$task_args" ]
then
    rally task start --task "$task_file" --task-args "$task_args"
else
    rally task start --task "$task_file"
fi

# Get UUID of Rally task using logs
$uuid_extractor_script $log_file

task_uuid=$(cat /etc/packer-utils/image-testing-rally/current_task_uuid.txt)

# Getting results of Rally task
#task

results_file_path="/etc/packer-utils/image-testing-rally/task-json-results/${task_uuid}.json"

rally task report $task_uuid --json --out $results_file_path

# Some method of aborting the test if it takes an abnormal amount of time - doesn't always work so a timeout that launches another Rally task?
# rally task abort --uuid [uuid]

# Get results of finished task into json file
