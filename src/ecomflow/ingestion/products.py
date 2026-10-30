"""Import CSV/Excel with row-level provenance and rejected-row reports."""
import json
from pathlib import Path
import pandas as pd
from ecomflow.core.models import Product, now
from ecomflow.database.store import Store

def read_table(path: str) -> pd.DataFrame:
    """Read values as strings so currency never travels through binary floats."""
    if Path(path).suffix.lower() == '.csv':
        return pd.read_csv(path, dtype=str, keep_default_na=False)
    if Path(path).suffix.lower() == '.xlsx':
        return pd.read_excel(path, dtype=str, keep_default_na=False)
    raise ValueError('Only .csv and .xlsx files are supported')

def import_products(store: Store, path: str, output: str = 'outputs') -> dict:
    frame = read_table(path)
    seen: set[str] = set()
    errors = []
    success = 0
    with store.transaction() as db:
        for number, raw in enumerate(frame.to_dict('records'), 2):
            sku = None
            error = None
            try:
                clean = {str(k).strip().lower(): str(v).strip() for k,v in raw.items()}
                clean['currency'] = clean.get('currency', 'USD').upper()
                value = clean.get('stock', '')
                if not value.isdigit():
                    raise ValueError('stock must be a nonnegative integer')
                clean['stock'] = int(value)
                product = Product.model_validate(clean)
                if product.sku in seen:
                    raise ValueError('duplicate SKU in input')
                seen.add(product.sku)
                values = product.model_dump(mode='json')
                cols = list(values)
                db.execute(f"INSERT INTO products({','.join(cols)}) VALUES({','.join('?' for _ in cols)}) ON CONFLICT(sku) DO UPDATE SET " + ','.join(f'{c}=excluded.{c}' for c in cols if c not in ('sku','created_at')), tuple(values.values()))
                sku = product.sku
                success += 1
            except (ValueError, TypeError) as exc:
                error = str(exc)
                errors.append({**raw, 'row_number': number, 'error': error})
            db.execute('INSERT INTO imports(source,row_number,raw,sku,error,created_at) VALUES(?,?,?,?,?,?)', (str(Path(path).resolve()),number,json.dumps(raw,ensure_ascii=False),sku,error,now()))
    Path(output).mkdir(parents=True,exist_ok=True)
    pd.DataFrame(errors, columns=list(frame.columns)+['row_number','error']).to_excel(Path(output)/'product_errors.xlsx',index=False)
    return {'total':len(frame),'success':success,'failed':len(errors)}
