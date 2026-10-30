"""Exercise controllable faults against an actual TCP HTTP server."""
import socket
import subprocess
import sys
import time
import requests
import pytest
from ecomflow.clients.api import APIClient,APIError,AuthenticationError
from ecomflow.core.models import Product,Bill
from ecomflow.adapters.platforms import PlatformAAdapter

@pytest.fixture
def server():
    with socket.socket() as sock:
        sock.bind(('127.0.0.1',0)); port=sock.getsockname()[1]
    process=subprocess.Popen([sys.executable,'-m','uvicorn','mock_platform.app:app','--port',str(port)],stdout=subprocess.DEVNULL,stderr=subprocess.DEVNULL)
    session=requests.Session(); session.trust_env=False
    url=f'http://127.0.0.1:{port}'
    try:
        for _ in range(100):
            try:
                if session.get(url+'/health',timeout=.1).status_code==200: break
            except requests.RequestException: pass
            time.sleep(.02)
        else: raise RuntimeError('server not ready')
        yield url,session
    finally:
        process.terminate()
        try: process.wait(timeout=3)
        except subprocess.TimeoutExpired: process.kill(); process.wait()
        session.close()

@pytest.mark.parametrize('kind',['401','429','500','timeout','invalid_json','duplicate'])
def test_actual_faults(server,kind):
    url,session=server
    session.post(url+'/control/platform_a/fault',json={'kind':kind,'count':3,'delay':.2},timeout=1).raise_for_status()
    api=APIClient(url,session=session,timeout=(1,.03),sleep=lambda _:None)
    with pytest.raises(AuthenticationError if kind=='401' else APIError): api.get('/platform_a/orders')
    session.post(url+'/control/platform_a/fault',json={'kind':'none','count':0},timeout=1).raise_for_status()
    assert api.get('/platform_a/orders')['orders']

def test_idempotency_and_payload_conflict(server):
    url,session=server; api=APIClient(url,session=session)
    p=Product(sku='X',title='Demo',price='0.10',currency='USD',stock=1)
    adapter=PlatformAAdapter(api)
    assert adapter.publish(p)==adapter.publish(p)
    with pytest.raises(APIError): adapter.publish(p.model_copy(update={'title':'Changed'}))
    assert api.get('/platform_a/products/X')['title']=='Demo'

def test_financial_models_reject_float():
    with pytest.raises(ValueError): Product(sku='X',title='x',price=.1,currency='USD',stock=1)
    with pytest.raises(ValueError): Bill(platform='platform_a',platform_order_id='X',currency='USD',gross_amount=.1,refund_amount='0',fee_amount='0',settlement_amount='0',settlement_date='2026-01-01')
