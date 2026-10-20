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
print("2.2.2 CHUẨN HÓA KIỂU DỮ LIỆU")
print("==========================================")

# Các cột cần chuyển sang kiểu dữ liệu số
numeric_columns = [
    "sale_price_vnd",
    "list_price_vnd",
    "quantity_sold",
    "rating",
    "review_count"
]

# Chuyển các cột số về kiểu numeric
for col in numeric_columns:
    df[col] = pd.to_numeric(
        df[col],
        errors="coerce"
    )

# Chuẩn hóa cột thời gian
df["crawled_at"] = pd.to_datetime(
    df["crawled_at"],
    errors="coerce"
)

# Chuẩn hóa cột availability
def clean_availability(value):

    # Nếu dữ liệu bị thiếu
    if pd.isna(value):
        return "Unknown"

    value = str(value).strip()

    # Trường hợp dữ liệu đã thể hiện InStock
    if "InStock" in value or "instock" in value.lower():
        return "InStock"

    # Trường hợp dữ liệu là số lượng tồn kho
    try:
        quantity = float(value)

        if quantity > 0:
            return "InStock"
        else:
            return "Unknown"

    except:
        return "Unknown"


df["availability"] = df["availability"].apply(
    clean_availability
)

# Kiểm tra kết quả chuẩn hóa
print("\nKiểu dữ liệu sau khi chuẩn hóa:")

print(df[numeric_columns].dtypes)

print("\nKiểu dữ liệu crawled_at:")
print(df["crawled_at"].dtype)

print("\nKiểu dữ liệu availability:")
print(df["availability"].dtype)

print("\nPhân bố availability sau chuẩn hóa:")
print(
    df["availability"]
    .value_counts(dropna=False)
)

# Kiểm tra giá trị thiếu phát sinh
print("\nSố giá trị thiếu sau khi chuyển đổi kiểu dữ liệu:")

for col in numeric_columns:
    print(
        f"{col}:",
        df[col].isna().sum()
    )

print(
    "crawled_at:",
    df["crawled_at"].isna().sum()
)

print(
    "availability:",
    df["availability"].isna().sum()
)


print("\n==========================================")
print("2.2.3 XỬ LÝ DỮ LIỆU THIẾU VÀ TRÙNG LẶP")
print("==========================================")

# Chuẩn hóa các giá trị được xem là thiếu
df = df.replace(
    [
        "Không có thông tin",
        "không có thông tin",
        "N/A",
        "n/a",
        "NA",
        "null",
        "None",
        ""
    ],
    pd.NA
)

# Xóa sản phẩm thiếu thông tin quan trọng
before_missing = len(df)

# Không có tên, giá bán hoặc brand → xóa
df = df.dropna(
    subset=[
        "name",
        "sale_price_vnd",
        "brand"
    ]
)

after_missing = len(df)

print("\nXử lý sản phẩm thiếu tên, giá hoặc brand:")
print("Số dòng trước:", before_missing)
print("Số dòng sau:", after_missing)
print(
    "Số dòng bị xóa:",
    before_missing - after_missing
)

# Chuẩn hóa tên sản phẩm
df["name"] = (
    df["name"]
    .astype(str)
    .str.strip()
    .str.replace(r"\s+", " ", regex=True)
)


# Chuẩn hóa tên thương hiệu

df["brand"] = (
    df["brand"]
    .astype(str)
    .str.strip()
    .str.replace(r"\s+", " ", regex=True)
)

brand_mapping = {
    "apple": "Apple",
    "samsung": "Samsung",
    "xiaomi": "Xiaomi",
    "oppo": "OPPO",
    "vivo": "Vivo",
    "asus": "ASUS",
    "acer": "Acer",
    "lenovo": "Lenovo",
    "hp": "HP",
    "dell": "Dell",
    "sony": "Sony",
    "lg": "LG",
    "jbl": "JBL"
}

brand_clean = df["brand"].str.lower()

df["brand"] = (
    brand_clean
    .map(brand_mapping)
    .fillna(df["brand"])
)


#  Xử lý các thuộc tính thiếu khác

# Giá niêm yết thiếu → dùng giá bán
df["list_price_vnd"] = df["list_price_vnd"].fillna(
    df["sale_price_vnd"]
)

# Xử lý dữ liệu trùng lặp

before_duplicate = len(df)

df = df.drop_duplicates()

after_duplicate = len(df)

print("\nXử lý dữ liệu trùng lặp:")
print("Số dòng trước:", before_duplicate)
print("Số dòng sau:", after_duplicate)
print(
    "Số dòng trùng bị xóa:",
    before_duplicate - after_duplicate
)


# Kiểm tra lại dữ liệu thiếu
print("\nDữ liệu thiếu sau khi xử lý:")
print(df.isnull().sum())

print("\n==========================================")
print("2.2.4 XỬ LÝ DỮ LIỆU KHÔNG HỢP LỆ")
print("==========================================")


# Xác định các điều kiện dữ liệu không hợp lệ
invalid_price = (
    df["sale_price_vnd"] <= 0
)

invalid_rating = (
    (df["rating"] < 0) |
    (df["rating"] > 5)
)

invalid_review = (
    df["review_count"] < 0
)

invalid_quantity = (
    df["quantity_sold"] < 0
)

# Giá bán lớn hơn giá niêm yết
invalid_price_order = (
    df["sale_price_vnd"] >
    df["list_price_vnd"]
)

# Đếm dữ liệu không hợp lệ

print("\nSố lượng dữ liệu không hợp lệ:")

print(
    "Giá bán <= 0:",
    invalid_price.sum()
)

print(
    "Rating ngoài khoảng 0-5:",
    invalid_rating.sum()
)

print(
    "Review_count âm:",
    invalid_review.sum()
)

print(
    "Quantity_sold âm:",
    invalid_quantity.sum()
)

print(
    "Giá bán > giá niêm yết:",
    invalid_price_order.sum()
)

# Loại bỏ dữ liệu không hợp lệ
before_invalid = len(df)

df = df[
    ~invalid_price &
    ~invalid_rating &
    ~invalid_review &
    ~invalid_quantity &
    ~invalid_price_order
].copy()

after_invalid = len(df)


print("\nKết quả xử lý dữ liệu không hợp lệ:")
print(
    "Số dòng trước:",
    before_invalid
)

print(
    "Số dòng sau:",
    after_invalid
)

print(
    "Số dòng bị loại:",
    before_invalid - after_invalid
)


# Kiểm tra lại sau khi xử lý

print("\nKiểm tra dữ liệu không hợp lệ sau khi xử lý:")

print(
    "Giá bán <= 0:",
    (df["sale_price_vnd"] <= 0).sum()
)

print(
    "Rating ngoài khoảng 0-5:",
    (
        (df["rating"] < 0) |
        (df["rating"] > 5)
    ).sum()
)

print(
    "Review_count âm:",
    (df["review_count"] < 0).sum()
)

print(
    "Quantity_sold âm:",
    (df["quantity_sold"] < 0).sum()
)

print(
    "Giá bán > giá niêm yết:",
    (
        df["sale_price_vnd"] >
        df["list_price_vnd"]
    ).sum()
)

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
