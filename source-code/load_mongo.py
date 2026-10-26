# 2.4.1 nạp dữ liệu vào MongoDB
import json
import os
import pandas as pd
from pymongo import MongoClient
from config import OUT, find_file, load_products

df = load_products().drop_duplicates("listing_id")

# Nhãn cụm từ K-Means (nếu đã chạy)
km_path = find_file("products_kmeans_result.csv")
if km_path:
    df = df.merge(pd.read_csv(km_path)[["listing_id", "cluster"]].drop_duplicates("listing_id"),
                  on="listing_id", how="left")
    df["cluster"] = df["cluster"].astype("Int64")
else:
    print("Chưa có products_kmeans_result.csv, bỏ qua nhãn cụm.")

# Cờ bất thường từ Isolation Forest (nếu đã chạy)
an_path = OUT / "tables" / "anomalies_result.csv"
if an_path.exists():
    a = pd.read_csv(an_path)[["listing_id", "is_anomaly", "anomaly_score",
                              "price_ratio_vs_median", "anomaly_reason"]]
    df = df.merge(a, on="listing_id", how="left")
    df["is_anomaly"] = df["is_anomaly"].fillna(False).astype(bool)
else:
    print("Chưa có anomalies_result.csv, bỏ qua cờ bất thường.")

records = json.loads(df.to_json(orient="records", force_ascii=False))   # NaN -> null

db = MongoClient(os.environ.get("MONGO_URI", "mongodb://localhost:27017"))["tech_market"]
db.products.delete_many({})
db.products.insert_many(records)
db.products.create_index("listing_id", unique=True)
for field in ("brand", "category_context", "source", "price_segment", "cluster", "is_anomaly"):
    db.products.create_index(field)
print("Đã nạp", db.products.count_documents({}), "sản phẩm vào MongoDB (tech_market.products)")