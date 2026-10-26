
import pandas as pd
df = pd.read_csv("products_clean.csv")
# Tổng số bản ghi
print("\n1. TỔNG SỐ SẢN PHẨM")
print("Tổng số bản ghi:", len(df))

# Số lượng sản phẩm theo website
print("\n2. SỐ LƯỢNG SẢN PHẨM THEO WEBSITE")

if "source" in df.columns:
    print(df["source"].value_counts().to_string())
else:
    print("Không tìm thấy cột source.")

# Thống kê giá bán
print("\n3. THỐNG KÊ GIÁ BÁN")

if "sale_price_vnd" in df.columns:
    gia_ban = pd.to_numeric(df["sale_price_vnd"], errors="coerce")
    gia_hop_le = gia_ban[gia_ban > 0].dropna()

    if len(gia_hop_le) > 0:
        print("Giá bán trung bình:", round(gia_hop_le.mean(), 0), "VND")
        print("Giá bán trung vị:", round(gia_hop_le.median(), 0), "VND")
        print("Giá bán thấp nhất:", gia_hop_le.min(), "VND")
        print("Giá bán cao nhất:", gia_hop_le.max(), "VND")
    else:
        print("Không có giá bán hợp lệ.")
else:
    print("Không tìm thấy cột sale_price_vnd.")

# Tính tỷ lệ sản phẩm giảm giá
print("\n4. TỶ LỆ SẢN PHẨM GIẢM GIÁ")

if "sale_price_vnd" in df.columns and "list_price_vnd" in df.columns:
    gia_ban = pd.to_numeric(df["sale_price_vnd"], errors="coerce")
    gia_niem_yet = pd.to_numeric(df["list_price_vnd"], errors="coerce")

    # Chỉ lấy bản ghi có cả hai mức giá lớn hơn 0
    co_du_gia = (
        gia_ban.notna()
        & gia_niem_yet.notna()
        & (gia_ban > 0)
        & (gia_niem_yet > 0)
    )

    so_ban_ghi_co_gia = co_du_gia.sum()
    giam_gia = co_du_gia & (gia_ban < gia_niem_yet)
    so_ban_ghi_giam_gia = giam_gia.sum()

    print("Số bản ghi đủ dữ liệu giá:", so_ban_ghi_co_gia)
    print("Số bản ghi có giảm giá:", so_ban_ghi_giam_gia)

    if so_ban_ghi_co_gia > 0:
        ty_le = so_ban_ghi_giam_gia / so_ban_ghi_co_gia * 100
        print("Tỷ lệ giảm giá:", round(ty_le, 2), "%")
    else:
        print("Không đủ dữ liệu để tính tỷ lệ giảm giá.")
else:
    print("Không đủ cột giá bán và giá niêm yết.")

# Thống kê đánh giá và số lượng đã bán
print("\n5. ĐÁNH GIÁ VÀ SỐ LƯỢNG ĐÃ BÁN")

if "rating" in df.columns:
    rating = pd.to_numeric(df["rating"], errors="coerce")
    rating_hop_le = rating.dropna()

    if len(rating_hop_le) > 0:
        print("Điểm đánh giá trung bình:", round(rating_hop_le.mean(), 2))
    else:
        print("Không có điểm đánh giá hợp lệ.")
else:
    print("Chưa có cột rating.")

if "review_count" in df.columns:
    review = pd.to_numeric(df["review_count"], errors="coerce")
    review_hop_le = review.dropna()

    if len(review_hop_le) > 0:
        print("Tổng lượt đánh giá ghi nhận:", review_hop_le.sum())
    else:
        print("Không có dữ liệu lượt đánh giá hợp lệ.")
else:
    print("Chưa có cột review_count.")

if "quantity_sold" in df.columns:
    da_ban = pd.to_numeric(df["quantity_sold"], errors="coerce")
    da_ban_hop_le = da_ban.dropna()

    if len(da_ban_hop_le) > 0:
        print("Tổng số lượng đã bán ghi nhận:", da_ban_hop_le.sum())
    else:
        print("Không có dữ liệu số lượng đã bán hợp lệ.")
else:
    print("Chưa có cột quantity_sold.")

# Các cột số liệu cần tìm giá trị nhỏ nhất và lớn nhất
cac_cot = [
    "sale_price_vnd",
    "list_price_vnd",
    "discount_percent",
    "rating",
    "review_count"
]

# Min-max trên toàn bộ dữ liệu
print("\n1. MIN-MAX TOÀN BỘ DỮ LIỆU")

for cot in cac_cot:
    if cot in df.columns:
        du_lieu = pd.to_numeric(df[cot], errors="coerce").dropna()

        # Với các cột giá, chỉ xét giá trị lớn hơn 0
        if cot in ["sale_price_vnd", "list_price_vnd"]:
            du_lieu = du_lieu[du_lieu > 0]

        if len(du_lieu) > 0:
            print(f"\n{cot}")
            print("Min:", du_lieu.min())
            print("Max:", du_lieu.max())
        else:
            print(f"\n{cot}: Không có dữ liệu hợp lệ.")
    else:
        print(f"\n{cot}: Không có cột này trong dữ liệu.")

# Min-max riêng theo từng website
print("\n2. MIN-MAX THEO TỪNG WEBSITE")

if "source" in df.columns:
    for website, nhom in df.groupby("source"):
        print(f"\n--- Website: {website} ---")

        for cot in cac_cot:
            if cot in nhom.columns:
                du_lieu = pd.to_numeric(
                    nhom[cot], errors="coerce"
                ).dropna()

                if cot in ["sale_price_vnd", "list_price_vnd"]:
                    du_lieu = du_lieu[du_lieu > 0]

                if len(du_lieu) > 0:
                    print(f"{cot}: Min = {du_lieu.min()}, "
                          f"Max = {du_lieu.max()}")
                else:
                    print(f"{cot}: Không có dữ liệu hợp lệ.")
else:
    print("Không thể thống kê theo website vì thiếu cột source.")


