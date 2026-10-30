"""Persistent task lifecycle and structured failure accounting."""
import logging
from pathlib import Path
from uuid import uuid4
from collections.abc import Callable
from ecomflow.core.models import now
from ecomflow.database.store import Store

log=logging.getLogger('ecomflow')

def configure_logging(directory: str='logs') -> None:
    Path(directory).mkdir(parents=True,exist_ok=True)
    root=logging.getLogger()
    root.setLevel(logging.INFO)
    target=str((Path(directory)/'ecomflow.log').resolve())
    if not any(isinstance(h,logging.FileHandler) and h.baseFilename==target for h in root.handlers):
        handler=logging.FileHandler(target,encoding='utf-8')
        handler.setFormatter(logging.Formatter('%(asctime)s %(levelname)s %(name)s %(message)s'))
        root.addHandler(handler)

class TaskFailed(RuntimeError):
    """A task finished with failed business records."""

class TaskRunner:
    def __init__(self,store: Store): self.store=store

    def run(self,kind: str,operation: Callable[[],dict],retry_of: str | None=None) -> dict:
        """Persist pending/running/final states; never swallow an operation error."""
        task_id=str(uuid4())
        retries=0
        if retry_of:
            previous=self.store.rows('SELECT * FROM tasks WHERE id=?',(retry_of,))
            if not previous or previous[0]['status']!='FAILED' or previous[0]['type']!=kind:
                raise ValueError('Retry requires a failed task of the same type')
            retries=previous[0]['retries']+1
            if retries>3: raise ValueError('Task retry limit reached')
        with self.store.transaction() as db:
            db.execute('INSERT INTO tasks(id,type,status,retries) VALUES(?,?,?,?)',(task_id,kind,'PENDING',retries))
        with self.store.transaction() as db:
            db.execute('UPDATE tasks SET status=?,started_at=? WHERE id=?',('RUNNING',now(),task_id))
            db.execute('INSERT INTO task_logs(task_id,created_at,message) VALUES(?,?,?)',(task_id,now(),f'Start {kind}; retry_of={retry_of}'))
        result={'total':0,'success':0,'failed':0}
        try:
            result.update(operation())
            if result['failed']:
                raise TaskFailed(f"{result['failed']} records failed; inspect row reports or listing errors")
        except Exception as exc:
            # An operation-wide failure is represented by one failed execution unit.
            if not result['failed']:
                result={'total':1,'success':0,'failed':1}
            self._finish(task_id,'FAILED',result,str(exc))
            log.exception('task failed id=%s type=%s',task_id,kind)
            raise
        self._finish(task_id,'SUCCESS',result,None)
        return {'task_id':task_id,**result}

    def _finish(self,task_id: str,status: str,result: dict,error: str | None) -> None:
        with self.store.transaction() as db:
            db.execute('UPDATE tasks SET status=?,ended_at=?,total=?,success=?,failed=?,error=? WHERE id=?',(status,now(),result['total'],result['success'],result['failed'],error,task_id))
            db.execute('INSERT INTO task_logs(task_id,created_at,message) VALUES(?,?,?)',(task_id,now(),error or 'Completed'))
        log.info('task completed id=%s status=%s total=%s success=%s failed=%s',task_id,status,result['total'],result['success'],result['failed'])
