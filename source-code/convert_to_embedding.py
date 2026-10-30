"""Convert cleaned flat CSV to MongoDB Extended JSON with embedded retailer/brand/category.
Run: python source-code/convert_to_embedding.py --input dataset/products_clean.csv --output dataset/products_embedding.json
"""
import argparse
import csv
import json
from datetime import datetime, timezone
from pathlib import Path

EXPECTED = ['listing_id','name','brand','source','category_context','sale_price_vnd',
            'list_price_vnd','quantity_sold','rating','review_count','availability',
            'product_url','crawled_at']
OPTIONAL_DERIVED = {'discount_percent','price_segment','estimated_revenue_vnd','rating_level'}

def integer(value, key, row_index):
    try:
        if value is None or not str(value).strip():
            raise ValueError('missing')
        number = float(value)
        if not number.is_integer():
            raise ValueError('not integer')
        return int(number)
    except (ValueError, OverflowError) as exc:
        raise ValueError(f'Row {row_index}: invalid integer {key}={value!r}') from exc

def decimal(value, key, row_index):
    try:
        if not str(value).strip():
            return None
        return float(value)
    except ValueError as exc:
        raise ValueError(f'Row {row_index}: invalid float {key}={value!r}') from exc

def convert_record(row, index):
    required = ['listing_id','name','source','brand','product_url','sale_price_vnd']
    for key in required:
        if not row[key].strip():
            raise ValueError(f'Row {index}: required value missing: {key}')
    sale = integer(row['sale_price_vnd'], 'sale_price_vnd', index)
    sold = integer(row['quantity_sold'], 'quantity_sold', index)
    count = integer(row['review_count'], 'review_count', index)
    rating = decimal(row['rating'], 'rating', index)
    list_price = decimal(row['list_price_vnd'], 'list_price_vnd', index)
    if sale <= 0 or sold < 0 or count < 0 or rating is None or not 0 <= rating <= 5:
        raise ValueError(f'Row {index}: invalid price, quantity, rating, or review_count')
    if list_price is not None and list_price <= 0:
        raise ValueError(f'Row {index}: invalid list_price_vnd')
    try:
        d = datetime.fromisoformat(row['crawled_at'].strip().replace('Z', '+00:00'))
        if d.tzinfo is None:
            raise ValueError('timezone missing')
        utc = d.astimezone(timezone.utc).isoformat(timespec='milliseconds').replace('+00:00','Z')
    except ValueError as exc:
        raise ValueError(f'Row {index}: invalid crawled_at') from exc
    return {
        'listing_id': row['listing_id'].strip(),
        'name': row['name'].strip(),
        'retailer': {'source': row['source'].strip()},
        'brand': {'brand': row['brand'].strip()},
        'category': {'category_context': row['category_context'].strip()},
        'sale_price_vnd': sale,
        'list_price_vnd': list_price,
        'quantity_sold': sold,
        'rating': rating,
        'review_count': count,
        'availability': row['availability'].strip(),
        'product_url': row['product_url'].strip(),
        'crawled_at': {'$date': utc}
    }

def convert(source, target):
    with source.open(encoding='utf-8-sig', newline='') as f:
        reader = csv.DictReader(f)
        missing = set(EXPECTED) - set(reader.fieldnames or [])
        if missing:
            raise ValueError(f'Missing CSV columns: {sorted(missing)}')
        rows = [convert_record(row, n) for n, row in enumerate(reader, start=2)]
    ids = [r['listing_id'] for r in rows]
    urls = [(r['retailer']['source'], r['product_url']) for r in rows]
    if len(set(ids)) != len(ids) or len(set(urls)) != len(urls):
        raise ValueError('Input has duplicate listing_id or (source, product_url); stop before import')
    target.parent.mkdir(parents=True, exist_ok=True)
    with target.open('w', encoding='utf-8') as f:
        json.dump(rows, f, indent=2, ensure_ascii=False, allow_nan=False)
    print('Input records:', len(rows))
    print('Output:', target)
    print('Embedded subdocuments:', 'retailer', 'brand', 'category')
    print('Example record:', json.dumps(rows[0], ensure_ascii=False, indent=2))
    return rows

if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--input', type=Path, default=Path('dataset/products_clean.csv'))
    parser.add_argument('--output', type=Path, default=Path('dataset/products_embedding.json'))
    options = parser.parse_args()
    convert(options.input, options.output)
