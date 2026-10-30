import pandas as pd
import pytest
from ecomflow.database.store import Store
from ecomflow.ingestion.products import import_products

@pytest.mark.parametrize('ext',['csv','xlsx'])
def test_product_import(tmp_path,ext):
    rows=[dict(sku='X',title='Title',price='1.20',currency='USD',stock='2'),dict(sku='',title='Bad',price='1',currency='USD',stock='2'),dict(sku='X',title='Duplicate',price='1',currency='USD',stock='2'),dict(sku='Y',title='Negative',price='-1',currency='USD',stock='2'),dict(sku='Z',title='Stock',price='1',currency='USD',stock='1.5')]
    path=tmp_path/f'products.{ext}'
    frame=pd.DataFrame(rows)
    if ext=='csv': frame.to_csv(path,index=False)
    else: frame.to_excel(path,index=False)
    store=Store(str(tmp_path/'db'))
    assert import_products(store,str(path),str(tmp_path))==dict(total=5,success=1,failed=4)
    assert store.rows('SELECT price FROM products')[0]['price']=='1.20'
    assert len(store.rows('SELECT * FROM imports'))==5
    assert (tmp_path/'product_errors.xlsx').exists()
