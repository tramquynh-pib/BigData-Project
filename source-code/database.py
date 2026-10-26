
import os
from dotenv import load_dotenv
from pymongo import MongoClient
from pymongo.server_api import ServerApi

load_dotenv()

uri = os.getenv("MONGODB_URI")

if not uri:
    raise ValueError(
        "Khong tim thay MONGODB_URI. "
        "Hay kiem tra file .env trong thu muc du an."
    )

client = MongoClient(
    uri,
    server_api=ServerApi("1"),
    serverSelectionTimeoutMS=10000
)

db = client["Technology_market_analysis"]
products = db["product_listings"]

try:
    client.admin.command("ping")
    print("KET NOI MONGODB THANH CONG!")
    print("Database:", db.name)
    print("Collection:", products.name)
    print("So luong san pham:", products.count_documents({}))

    print("\nSAN PHAM MAU:")
    print(products.find_one({}, {"_id": 0, "name": 1, "brand": 1,
                                 "category": 1, "sale_price_vnd": 1}))

except Exception as e:
    print("KET NOI THAT BAI:", type(e).__name__)
    print(e)

except Exception as e:
    print("KET NOI THAT BAI:", type(e).__name__)
    print(e)