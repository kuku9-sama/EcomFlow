"""Publish canonical products while preserving per-platform outcomes."""
import logging
from ecomflow.core.models import Product
from ecomflow.database.store import Store
from ecomflow.adapters.platforms import PlatformAdapter

log=logging.getLogger(__name__)

def publish_products(store: Store,adapter: PlatformAdapter,sku: str | None=None) -> dict:
    products=store.rows('SELECT * FROM products'+(' WHERE sku=?' if sku else ''),(sku,) if sku else ())
    result={'total':len(products),'success':0,'failed':0}
    for row in products:
        existing=store.rows('SELECT * FROM platform_listings WHERE platform=? AND sku=?',(adapter.name,row['sku']))
        if existing and existing[0]['status']=='SUCCESS':
            result['success']+=1
            continue
        external_id=None
        error=None
        try:
            external_id=adapter.publish(Product.model_validate(row))
            status='SUCCESS'
            result['success']+=1
        except Exception as exc:
            status='FAILED'; error=str(exc); result['failed']+=1
            log.exception('publish failed platform=%s sku=%s',adapter.name,row['sku'])
        with store.transaction() as db:
            db.execute('INSERT INTO platform_listings(platform,sku,status,external_id,error,attempts) VALUES(?,?,?,?,?,1) ON CONFLICT(platform,sku) DO UPDATE SET status=excluded.status,external_id=excluded.external_id,error=excluded.error,attempts=platform_listings.attempts+1',(adapter.name,row['sku'],status,external_id,error))
    return result
