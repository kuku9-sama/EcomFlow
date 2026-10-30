import pytest
from ecomflow.adapters.platforms import PlatformAAdapter,PlatformBAdapter
from ecomflow.services.orders import sync_orders
from ecomflow.database.store import Store
from ecomflow.core.models import Order

class Adapter:
    name='platform_a'
    def __init__(self,fail=False): self.fail=fail; self.cursors=[]
    def orders(self,page,cursor):
        self.cursors.append(cursor)
        if page==2 and self.fail: raise RuntimeError('page failed')
        return [Order(platform=self.name,platform_order_id=str(page),currency='USD',gross_amount='10.00',status='PAID',updated_at=f'2026-01-0{page}',items=[{'sku':'X','quantity':1,'unit_price':'10.00'}])],page<2

def test_repeat_sync(tmp_path):
    store=Store(str(tmp_path/'db')); adapter=Adapter()
    assert sync_orders(store,adapter)['success']==2
    assert sync_orders(store,adapter)['success']==2
    assert len(store.rows('SELECT * FROM orders'))==2
    assert len(store.rows('SELECT * FROM order_items'))==2
    assert adapter.cursors[-1]=='2026-01-02'

def test_failed_page_rollback(tmp_path):
    store=Store(str(tmp_path/'db'))
    with pytest.raises(RuntimeError): sync_orders(store,Adapter(True))
    assert not store.rows('SELECT * FROM orders')
    assert not store.rows('SELECT * FROM sync_state')

def test_status_mapping():
    a={'orders':[{'order_id':'A','currency':'USD','total':'1.00','state':'shipped','updated_at':'2026','items':[{'sku':'X','qty':1,'price':'1.00'}]}],'has_more':False}
    b={'data':[{'number':'B','money':{'currency':'USD','gross':'1.00'},'status_code':'VOID','modified':'2026','lines':[{'seller_code':'X','units':1,'unit_amount':'1.00'}]}],'pagination':{'next':None}}
    assert PlatformAAdapter(None).parse_page(a)[0][0].status=='SHIPPED'
    assert PlatformBAdapter(None).parse_page(b)[0][0].status=='CANCELLED'
