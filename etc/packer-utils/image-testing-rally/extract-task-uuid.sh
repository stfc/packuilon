#!/bin/bash

log_file=$1

task_uuid_cmd=$(cat $log_file | grep -m 1 "Task")
echo $task_uuid_cmd

if [ -n "$task_uuid_cmd" ]
then
    task_uuid=$(echo $task_uuid_cmd | grep -Eo "[a-z0-9]{8}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{4}-[a-z0-9]{12}")
    echo 'UUID: '$task_uuid
    echo -n $task_uuid > /etc/packer-utils/image-testing-rally/current_task_uuid.txt
else
    echo 'No task UUID found during search of logs'
    echo $(cat $log_file)
fi
