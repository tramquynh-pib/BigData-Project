import pandas as pd
import os


# Đọc dữ liệu gốc
df = pd.read_csv("market_listings_new.csv")

print("\n==========================================")
print("2.2.1 KHẢO SÁT CHẤT LƯỢNG DỮ LIỆU")
print("==========================================")

# Số dòng và số cột
print("Số dòng:", df.shape[0])
print("Số cột:", df.shape[1])

# Danh sách cột
print("\nDanh sách cột:")
print(df.columns.tolist())

# Kiểu dữ liệu
print("\nKiểu dữ liệu:")
print(df.dtypes)

# Dữ liệu thiếu
print("\nDữ liệu thiếu:")
print(df.isnull().sum())

# Dữ liệu trùng
print("\nSố dòng trùng:")
print(df.duplicated().sum())

# Thống kê các biến số
print("\nThống kê dữ liệu số:")
print(
    df[
        [
            "sale_price_vnd",
            "list_price_vnd",
            "quantity_sold",
            "rating",
            "review_count"
        ]
    ].describe()
)
print("\n==========================================")
print("2.2.2 XỬ LÝ DỮ LIỆU THIẾU VÀ TRÙNG")
print("==========================================")

selected_columns = [
    "name",
    "brand",
    "source",
    "category_context",
    "sale_price_vnd",
    "list_price_vnd",
    "quantity_sold",
    "rating",
    "review_count",
    "availability",
    "product_url",
    "crawled_at",
    "listing_id"
]

df = df[selected_columns].copy()

print("Số cột sau khi chọn:", df.shape[1])
print("Các cột được giữ lại:")
print(df.columns.tolist())
# Xử lý brand thiếu
df["brand"] = df["brand"].fillna("Unknown")

# Xử lý availability thiếu
df["availability"] = df["availability"].fillna("Unknown")

# Xử lý list_price thiếu
df["list_price_vnd"] = df["list_price_vnd"].fillna(
    df["sale_price_vnd"]
)

print("\nDữ liệu thiếu sau khi xử lý:")
print(df.isnull().sum())
before = len(df)

df = df.drop_duplicates()

after = len(df)

print("\nSố dòng trước khi loại trùng:", before)
print("Số dòng sau khi loại trùng:", after)
print("Số dòng bị loại:", before - after)
print("\n==========================================")
print("2.2.3 CHUẨN HÓA KIỂU DỮ LIỆU")
print("==========================================")

# Các cột số
df["sale_price_vnd"] = pd.to_numeric(
    df["sale_price_vnd"],
    errors="coerce"
)

df["list_price_vnd"] = pd.to_numeric(
    df["list_price_vnd"],
    errors="coerce"
)

df["quantity_sold"] = pd.to_numeric(
    df["quantity_sold"],
    errors="coerce"
)

df["rating"] = pd.to_numeric(
    df["rating"],
    errors="coerce"
)

df["review_count"] = pd.to_numeric(
    df["review_count"],
    errors="coerce"
)

# Ngày thu thập
df["crawled_at"] = pd.to_datetime(
    df["crawled_at"],
    errors="coerce"
)

print("\nKiểu dữ liệu sau chuẩn hóa:")
print(df.dtypes)
print("\n==========================================")
print("2.2.4 XỬ LÝ DỮ LIỆU KHÔNG HỢP LỆ")
print("==========================================")

print(
    "Giá bán <= 0:",
    (df["sale_price_vnd"] <= 0).sum()
)

print(
    "Giá niêm yết <= 0:",
    (df["list_price_vnd"] <= 0).sum()
)

print(
    "Rating ngoài khoảng 0-5:",
    (
        (df["rating"] < 0) |
        (df["rating"] > 5)
    ).sum()
)

print(
    "Review âm:",
    (df["review_count"] < 0).sum()
)

print(
    "Số lượng bán âm:",
    (df["quantity_sold"] < 0).sum()
)

print(
    "Giá bán lớn hơn giá niêm yết:",
    (
        df["sale_price_vnd"] >
        df["list_price_vnd"]
    ).sum()
)
# ==========================================
# 2.2.5 TẠO THUỘC TÍNH PHỤC VỤ PHÂN TÍCH
# ==========================================

print("\n==========================================")
print("2.2.5 TẠO THUỘC TÍNH PHỤC VỤ PHÂN TÍCH")
print("==========================================")

# 1. Tính phần trăm giảm giá
df["discount_percent"] = (
    (df["list_price_vnd"] - df["sale_price_vnd"])
    / df["list_price_vnd"]
) * 100

df["discount_percent"] = (
    df["discount_percent"]
    .clip(lower=0, upper=100)
    .round(2)
)

# 2. Phân khúc giá
def price_segment(price):
    if price < 5000000:
        return "Budget"
    elif price < 10000000:
        return "Mid-range"
    elif price < 20000000:
        return "Upper-mid"
    else:
        return "Premium"

df["price_segment"] = df["sale_price_vnd"].apply(
    price_segment
)

# 3. Phân loại mức đánh giá
def rating_level(rating):
    if rating < 3:
        return "Low"
    elif rating <= 4:
        return "Medium"
    else:
        return "High"

df["rating_level"] = df["rating"].apply(
    rating_level
)

# 4. Tính doanh thu ước tính
df["estimated_revenue_vnd"] = (
    df["sale_price_vnd"] *
    df["quantity_sold"]
)

# Kiểm tra kết quả
print("\nCác thuộc tính mới:")
print(
    df[
        [
            "discount_percent",
            "price_segment",
            "rating_level",
            "estimated_revenue_vnd"
        ]
    ].head(10)
)
print("\n==========================================")
print("2.2.6 XUẤT DATASET SẠCH")
print("==========================================")

final_columns = [
    "listing_id",
    "name",
    "brand",
    "source",
    "category_context",
    "sale_price_vnd",
    "list_price_vnd",
    "discount_percent",
    "price_segment",
    "quantity_sold",
    "estimated_revenue_vnd",
    "rating",
    "rating_level",
    "review_count",
    "availability",
    "product_url",
    "crawled_at"
]

clean_df = df[final_columns].copy()

# Tạo thư mục data/cleaned
os.makedirs("data/cleaned", exist_ok=True)

# Xuất CSV
output_path = "data/cleaned/products_clean.csv"

clean_df.to_csv(
    output_path,
    index=False,
    encoding="utf-8-sig"
)

print("Dataset sạch đã được lưu tại:")
print(output_path)

print("\nKích thước dataset sạch:")
print(clean_df.shape)

print("\nDanh sách cột cuối cùng:")
print(clean_df.columns.tolist())

print("\n5 dòng đầu tiên:")
print(clean_df.head())
