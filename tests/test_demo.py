from ecomflow.cli import run_demo
from ecomflow.database.store import Store

def test_real_http_demo_repeatable(tmp_path):
    store=Store(str(tmp_path/'demo.sqlite'))
    first=run_demo(store,str(tmp_path))
    second=run_demo(store,str(tmp_path))
    for result in [first,second]:
        assert result['counts']['products']==2
        assert result['counts']['platform_listings']==4
        assert result['counts']['orders']==8
        assert result['counts']['order_items']==8
        assert result['counts']['bills']==8
    assert second['counts']['tasks']==12
    assert len(store.rows("SELECT * FROM tasks WHERE status='FAILED'"))==2
