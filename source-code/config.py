# version 2.4.0
import re
from pathlib import Path
import numpy as np
import pandas as pd

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
OUT = HERE / "outputs"
for sub in ("figures", "tables", "models"):
    (OUT / sub).mkdir(parents=True, exist_ok=True)

def find_file(name):
    """Tìm file ở source-code, dataset, thư mục gốc repo hoặc thư mục đang chạy."""
    for folder in (HERE, ROOT / "dataset", ROOT, HERE / "data" / "cleaned", Path.cwd()):
        p = folder / name
        if p.exists():
            return p
    for folder in (ROOT / "dataset", HERE / "data"):
        if folder.exists():
            hits = list(folder.rglob(name))
            if hits:
                return hits[0]
    return None

def parse_specs(name):
    vals = [int(n) * (1024 if u.upper() == "TB" else 1)
            for n, u in re.findall(r"(\d+)\s?(GB|TB)", str(name), flags=re.I)]
    if len(vals) >= 2:
        return min(vals), max(vals)      # RAM, bộ nhớ
    if len(vals) == 1:
        return np.nan, vals[0]
    return np.nan, np.nan

def load_products():
    path = find_file("products_clean.csv")
    if path is None:
        raise SystemExit("Không tìm thấy products_clean.csv. Chạy data-cleaning.py trước.")
    print("Đọc dữ liệu:", path)
    df = pd.read_csv(path)
    for col in ["sale_price_vnd", "list_price_vnd", "discount_percent", "quantity_sold",
                "estimated_revenue_vnd", "rating", "review_count"]:
        if col in df:
            df[col] = pd.to_numeric(df[col], errors="coerce")
    df["brand"] = df["brand"].fillna("Khác")
    df[["ram_gb", "storage_gb"]] = df["name"].apply(lambda s: pd.Series(parse_specs(s)))
    return df