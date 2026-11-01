"""Framework-only queue probe; no model or robot behavior."""
import json
import os
from pathlib import Path
from huey import SqliteHuey
root=Path(os.environ['PUPPYPI_QUEUE_PROBE_DIR'])
huey=SqliteHuey('puppypi_research_probe',filename=str(root/'queue.sqlite3'),immediate=False)
@huey.task(retries=0)
def marker_task(marker):
    return {'marker':marker,'worker_pid':os.getpid()}
@huey.task(retries=0)
def failing_task():
    with (root/'failure-attempts.jsonl').open('a') as f:
        f.write(json.dumps({'worker_pid':os.getpid()})+'\n')
    raise RuntimeError('Expected offline framework probe failure')
