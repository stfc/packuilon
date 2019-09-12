#!/bin/sh

deployment_uuid=$1
task_file=$2
# Keep this as final argument so it can be optional
task_file_args=$3

if [ -n "$task_files_args" ]
then
    task_args_option=" --task-args-file ${task_file_args}"
fi

# Deployment explictly set in case of multiple deployments on the machine
# Pass this UUID
rally deployment use $deployment_uuid

# rally-task-boot-and-delete.json-1568276636.log
# 

# Pass the file name - task-args-file is optional
rally task start --task $task_file $task_args_option

# Some method of aborting the test if it takes an abnormal amount of time - doesn't always work so a timeout that launches another Rally task?
# rally task abort --uuid [uuid]

# Get results of finished task into json file
# 
