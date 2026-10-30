import pandas as pd
import pytest
from ecomflow.database.store import Store
from ecomflow.services.reconciliation import import_bills,reconcile

@pytest.mark.parametrize('ext',['csv','xlsx'])
def test_reconciliation(tmp_path,ext):
    store=Store(str(tmp_path/'db'))
    with store.transaction() as db:
        for platform,prefix in [('platform_a','A'),('platform_b','B')]:
            for i in range(1,5):
                db.execute('INSERT INTO orders(platform,platform_order_id,currency,gross_amount,status,updated_at,synced_at) VALUES(?,?,?,?,?,?,?)',(platform,f'{prefix}-{i:03}','USD','20.00' if i%2 else '30.00','PAID','now','now'))
    path='data/sample_bills.csv'
    if ext=='xlsx':
        path=str(tmp_path/'bills.xlsx')
        pd.read_csv('data/sample_bills.csv',dtype=str).to_excel(path,index=False)
    assert import_bills(store,path)==8
    assert import_bills(store,path)==8
    assert len(store.rows('SELECT * FROM bills'))==8
    result=reconcile(store,str(tmp_path/'report.xlsx'))
    statuses=' '.join(r['status'] for r in result)
    for status in ['MATCHED','AMOUNT_MISMATCH','MISSING_BILL','DUPLICATE_BILL','CURRENCY_MISMATCH','ORPHAN_BILL']: assert status in statuses
    difference=next(r for r in result if r['platform_order_id']=='A-002')['difference']
    assert difference=='-1.00'
    assert len(pd.read_excel(tmp_path/'report.xlsx'))==10
