from rally_task_execute import RallyTaskExecution
from rally_task_analysis import RallyTaskAnalysis
from syslog import syslog, LOG_ERR, LOG_INFO

build_file_path = "/etc/packer-utils/build/nubes-unmanaged-nogui-sl7x-x86_64.nubes-unmanaged-nogui.json.json"

syslog(LOG_INFO, 'STARTING TO EXECUTE RALLY TASK')
RallyTaskExecution().execute_rally_task(build_file_path)
RallyTaskAnalysis().test_analysis()
