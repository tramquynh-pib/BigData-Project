
import pandas as pd
df = pd.read_csv("products_clean.csv")

# Thống kê tổng số bản ghi
print("TỔNG QUAN DỮ LIỆU")
print("Tổng số sản phẩm được thu thập:", len(df))

# Thống kê số sản phẩm theo website
print("SỐ LƯỢNG SẢN PHẨM THEO WEBSITE")

if "source" in df.columns:
    print(df["source"].value_counts().to_string())
else:
    print("Không tìm thấy cột source.")

# Thống kê giá bán
print("THỐNG KÊ GIÁ BÁN")

if "sale_price_vnd" in df.columns:
    # Chuyển giá bán thành kiểu số để tính toán
    gia_ban = pd.to_numeric(df["sale_price_vnd"], errors="coerce")
    gia_hop_le = gia_ban.dropna()

    if len(gia_hop_le) > 0:
        print("Giá bán trung bình:", round(gia_hop_le.mean(), 0), "VND")
        print("Giá bán trung vị:", round(gia_hop_le.median(), 0), "VND")
        print("Giá bán thấp nhất:", gia_hop_le.min(), "VND")
        print("Giá bán cao nhất:", gia_hop_le.max(), "VND")
    else:
        print("Không có dữ liệu giá bán hợp lệ.")
else:
    print("Không tìm thấy cột sale_price_vnd.")

# Tính tỷ lệ sản phẩm giảm giá
print("TỶ LỆ SẢN PHẨM GIẢM GIÁ")

if "sale_price_vnd" in df.columns and "list_price_vnd" in df.columns:
    gia_ban = pd.to_numeric(df["sale_price_vnd"], errors="coerce")
    gia_niem_yet = pd.to_numeric(df["list_price_vnd"], errors="coerce")

    # Chỉ xét các bản ghi có đủ hai mức giá hợp lệ
    co_du_gia = (
        gia_ban.notna()
        & gia_niem_yet.notna()
        & (gia_ban > 0)
        & (gia_niem_yet > 0)
    )

    so_ban_ghi_co_gia = co_du_gia.sum()

    giam_gia = co_du_gia & (gia_ban < gia_niem_yet)
    so_san_pham_giam_gia = giam_gia.sum()

    print("Số bản ghi có đủ dữ liệu giá:", so_ban_ghi_co_gia)
    print("Số bản ghi có giá giảm:", so_san_pham_giam_gia)

    if so_ban_ghi_co_gia > 0:
        ty_le = so_san_pham_giam_gia / so_ban_ghi_co_gia * 100
        print("Tỷ lệ giảm giá:", round(ty_le, 2), "%")
    else:
        print("Không đủ dữ liệu để tính tỷ lệ giảm giá.")
else:
    print("Không đủ cột giá bán và giá niêm yết.")

# Thống kê đánh giá và số lượng đã bán
print("ĐÁNH GIÁ VÀ SỐ LƯỢNG ĐÃ BÁN")

if "rating" in df.columns:
    rating = pd.to_numeric(df["rating"], errors="coerce")
    print("Điểm đánh giá trung bình:", round(rating.mean(), 2)
          if rating.notna().any() else "Chưa có dữ liệu hợp lệ")
else:
    print("Chưa có cột rating.")

if "review_count" in df.columns:
    review = pd.to_numeric(df["review_count"], errors="coerce")
    print("Tổng lượt đánh giá ghi nhận:", round(review.sum(), 0)
          if review.notna().any() else "Chưa có dữ liệu hợp lệ")
else:
    print("Chưa có cột review_count.")

if "quantity_sold" in df.columns:
    da_ban = pd.to_numeric(df["quantity_sold"], errors="coerce")
    print("Tổng số lượng đã bán ghi nhận:", round(da_ban.sum(), 0)
          if da_ban.notna().any() else "Chưa có dữ liệu hợp lệ")
else:
    print("Chưa có cột quantity_sold.")


