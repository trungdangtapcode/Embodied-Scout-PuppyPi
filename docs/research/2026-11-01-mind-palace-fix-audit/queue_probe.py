"""Exercise actual SqliteHuey enqueue/consumer/result/error across processes."""
import importlib.metadata
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import time
base=Path(__file__).resolve().parent
root=Path(tempfile.mkdtemp(prefix='queue-',dir=base))
os.environ['PUPPYPI_QUEUE_PROBE_DIR']=str(root)
from queue_tasks import huey,marker_task,failing_task
from huey.exceptions import TaskException
result={'profile':'offline framework-only subprocess test','framework':'huey','version':importlib.metadata.version('huey'),'backend':'SqliteHuey','live_api_calls':0,'robot_used':False,'parent_pid':os.getpid(),'status':'FAIL'}
consumer=None
try:
    ok=marker_task('queue-probe')
    failed=failing_task()
    result['queued_before_consumer']=huey.pending_count()
    with (root/'consumer.log').open('w') as log:
        consumer=subprocess.Popen([sys.executable,'-m','huey.bin.huey_consumer','queue_tasks.huey','-k','thread','-w','1','-d','0.05','-m','0.1','--no-periodic','--quiet'],cwd=base,stdout=log,stderr=log,env=os.environ.copy())
        deadline=time.monotonic()+15
        value=None
        error_observed=False
        while time.monotonic()<deadline:
            if value is None: value=ok.get(blocking=False)
            try:
                failed.get(blocking=False)
            except TaskException:
                error_observed=True
            if value is not None and error_observed: break
            if consumer.poll() is not None: raise RuntimeError('Consumer exited before results')
            time.sleep(0.05)
        result['task_result']=value
        result['task_error_observed']=error_observed
        result['failure_attempts']=len((root/'failure-attempts.jsonl').read_text().splitlines()) if (root/'failure-attempts.jsonl').exists() else 0
        result['queue_remaining']=huey.pending_count()
        if value is None or value['worker_pid']==os.getpid() or not error_observed or result['failure_attempts']!=1 or result['queue_remaining']!=0:
            raise RuntimeError('Queue isolation/result/failure contract did not pass')
        result['status']='PASS_FRAMEWORK_PROBE'
except Exception as e:
    result['error_type']=type(e).__name__
    result['error']=str(e)
finally:
    if consumer is not None:
        consumer.terminate()
        try: consumer.wait(timeout=10)
        except subprocess.TimeoutExpired:
            consumer.kill(); consumer.wait(timeout=5)
        result['consumer_stopped']=consumer.poll() is not None
(base/'queue-probe.json').write_text(json.dumps(result,indent=2)+'\n')
print(json.dumps(result,indent=2))
