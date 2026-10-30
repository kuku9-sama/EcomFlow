"""Command-line entry points and reproducible end-to-end demonstration."""
import argparse
import json
import os
from pathlib import Path
import socket
import subprocess
import sys
import time
import requests
from ecomflow.database.store import Store
from ecomflow.core.models import Product
from ecomflow.clients.api import APIClient
from ecomflow.adapters.platforms import adapter_for
from ecomflow.ingestion.products import import_products,read_table
from ecomflow.services.publishing import publish_products
from ecomflow.services.orders import sync_orders
from ecomflow.services.reconciliation import import_bills,reconcile
from ecomflow.jobs.tasks import TaskRunner,TaskFailed,configure_logging
from ecomflow.reports.summary import report


def init_demo() -> dict:
    """Generate Excel companions without replacing any existing input files."""
    for name in ['sample_products','sample_bills']:
        target=Path('data')/f'{name}.xlsx'
        if not target.exists(): read_table(str(Path('data')/f'{name}.csv')).to_excel(target,index=False)
    return {'status':'demo inputs initialized; all records fictional'}


def run_demo(store: Store,output: str='outputs') -> dict:
    """Run an isolated local mock server and always stop the owned process."""
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    url=f'http://127.0.0.1:{port}'
    Path(output).mkdir(parents=True,exist_ok=True)
    session=requests.Session(); session.trust_env=False
    with open(Path(output)/'mock-server.log','w') as logfile:
        process=subprocess.Popen([sys.executable,'-m','uvicorn','mock_platform.app:app','--host','127.0.0.1','--port',str(port)],stdout=logfile,stderr=subprocess.STDOUT)
        try:
            for _ in range(100):
                if process.poll() is not None: raise RuntimeError('Mock server exited; inspect mock-server.log')
                try:
                    response=session.get(url+'/health',timeout=0.2)
                    if response.status_code==200 and response.json()['status']=='ok': break
                except requests.RequestException: pass
                time.sleep(0.05)
            else: raise RuntimeError('Mock server readiness timeout')
            runner=TaskRunner(store)
            # The sample intentionally has invalid rows; preserve a FAILED import task.
            try:
                runner.run('import-products',lambda:import_products(store,'data/sample_products.csv',output))
            except TaskFailed: pass
            client=APIClient(url,session=session)
            for platform in ['platform_a','platform_b']:
                adapter=adapter_for(platform,client)
                # Restore successful demo listings into this new in-memory mock.
                for row in store.rows("SELECT p.* FROM products p JOIN platform_listings l ON p.sku=l.sku WHERE l.platform=? AND l.status='SUCCESS'",(platform,)):
                    adapter.publish(Product.model_validate(row))
                runner.run(f'publish-products:{platform}',lambda a=adapter:publish_products(store,a))
                for row in store.rows('SELECT sku FROM products'):
                    remote=client.get(f'/{platform}/products/{row["sku"]}')
                    if not remote: raise RuntimeError('Published listing missing from mock')
                # Full refresh is idempotent; demo works with a fresh mock on every run.
                runner.run(f'sync-orders:{platform}',lambda a=adapter:sync_orders(store,a,full=True))
            def reconcile_operation():
                import_bills(store,'data/sample_bills.csv')
                rows=reconcile(store,str(Path(output)/'reconciliation.xlsx'))
                return dict(total=len(rows),success=len(rows),failed=0)
            runner.run('reconcile',reconcile_operation)
            counts=report(store,str(Path(output)/'operations.xlsx'))
            return {'status':'demo completed','counts':counts,'reports':[str(Path(output)/'reconciliation.xlsx'),str(Path(output)/'operations.xlsx')],'note':'invalid sample product rows are recorded as one failed import task'}
        finally:
            process.terminate()
            try: process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill(); process.wait()
            session.close()


def main() -> int:
    parser=argparse.ArgumentParser(description='EcomFlow — fictional multi-channel commerce automation')
    parser.add_argument('--db',default=os.getenv('ECOMFLOW_DB','outputs/ecomflow.sqlite3'))
    parser.add_argument('--api-url',default=os.getenv('ECOMFLOW_API_URL','http://127.0.0.1:8000'))
    commands=parser.add_subparsers(dest='command',required=True)
    for name in ['init-db','init-demo','demo','report']: commands.add_parser(name)
    for name in ['import-products','reconcile']:
        sub=commands.add_parser(name); sub.add_argument('--file',required=True); sub.add_argument('--retry-of')
    for name in ['publish-products','sync-orders']:
        sub=commands.add_parser(name); sub.add_argument('--platform',required=True,choices=['platform_a','platform_b']); sub.add_argument('--retry-of')
        if name=='publish-products': sub.add_argument('--sku')
        else: sub.add_argument('--full',action='store_true')
    sub=commands.add_parser('listings'); sub.add_argument('--platform',required=True,choices=['platform_a','platform_b']); sub.add_argument('--sku')
    commands.add_parser('tasks')
    args=parser.parse_args()
    configure_logging()
    store=Store(args.db); runner=TaskRunner(store)
    try:
        if args.command=='init-db': result={'status':'database initialized','path':args.db}
        elif args.command=='init-demo': result=init_demo()
        elif args.command=='demo': result=run_demo(store)
        elif args.command=='report': result=report(store)
        elif args.command=='tasks': result=store.rows('SELECT * FROM tasks ORDER BY started_at')
        elif args.command=='listings':
            result=store.rows('SELECT * FROM platform_listings WHERE platform=?'+(' AND sku=?' if args.sku else ''),(args.platform,args.sku) if args.sku else (args.platform,))
        elif args.command=='import-products': result=runner.run('import-products',lambda:import_products(store,args.file),args.retry_of)
        elif args.command=='reconcile':
            def operation():
                import_bills(store,args.file); rows=reconcile(store)
                return dict(total=len(rows),success=len(rows),failed=0)
            result=runner.run('reconcile',operation,args.retry_of)
        else:
            client=APIClient(args.api_url)
            # Only loopback destinations are accepted by APIClient.
            client.session.trust_env=False
            adapter=adapter_for(args.platform,client)
            operation=(lambda:publish_products(store,adapter,args.sku)) if args.command=='publish-products' else (lambda:sync_orders(store,adapter,args.full))
            try: result=runner.run(f'{args.command}:{args.platform}',operation,args.retry_of)
            finally: client.session.close()
        print(json.dumps(result,ensure_ascii=False,indent=2))
        return 0
    except Exception as exc:
        import logging
        logging.getLogger(__name__).exception('command failed: %s',args.command)
        print(f'Error: {exc}',file=sys.stderr)
        return 1

if __name__=='__main__':
    raise SystemExit(main())
