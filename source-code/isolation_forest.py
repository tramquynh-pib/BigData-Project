
import os
import numpy as np
import pandas as pd

from sklearn.ensemble import IsolationForest
from database import products
from pymongo import UpdateOne


def main():
    print("=" * 60)
    print("ISOLATION FOREST - PHAT HIEN GIA BAT THUONG")
    print("=" * 60)

    # 1. Doc du lieu tu MongoDB
    documents = list(products.find({}, {"_id": 0}))
    df = pd.json_normalize(documents)

    print("Tong so san pham:", len(df))

    # 2. Chuan hoa cac truong du lieu
    df["sale_price_vnd"] = pd.to_numeric(
        df["sale_price_vnd"], errors="coerce"
    )

    df["list_price_vnd"] = pd.to_numeric(
        df["list_price_vnd"], errors="coerce"
    )

    df["category_name"] = (
        df["category.category_context"].fillna("Khong ro")
    )

    df["brand_name"] = (
        df["brand.brand"].fillna("Khong ro")
    )

    df["retailer_name"] = (
        df["retailer.source"].fillna("Khong ro")
    )

    df = df[
        df["sale_price_vnd"].notna()
        & (df["sale_price_vnd"] > 0)
    ].copy()

    # 3. Log gia de giam anh huong cua do lech gia rat lon
    df["log_sale_price"] = np.log1p(df["sale_price_vnd"])

    # Ty le chiet khau chi tinh duoc khi gia niem yet hop le
    df["discount_rate"] = np.nan

    valid_list_price = (
        df["list_price_vnd"].notna()
        & (df["list_price_vnd"] > 0)
        & (df["list_price_vnd"] >= df["sale_price_vnd"])
    )

    df.loc[valid_list_price, "discount_rate"] = (
        1
        - df.loc[valid_list_price, "sale_price_vnd"]
        / df.loc[valid_list_price, "list_price_vnd"]
    )

    # 4. Tao cot ket qua
    df["anomaly_label"] = "Chua danh gia"
    df["anomaly_score"] = np.nan

    # 5. Phat hien bat thuong rieng trong tung danh muc
    # Danh muc qua it san pham se duoc bo qua
    MIN_GROUP_SIZE = 15
    CONTAMINATION = 0.05

    for category, group in df.groupby("category_name"):
        if len(group) < MIN_GROUP_SIZE:
            df.loc[group.index, "anomaly_label"] = (
                "Khong du du lieu trong danh muc"
            )
            continue

        features = group[["log_sale_price", "discount_rate"]].copy()

        # Khong co gia niem yet hop le thi chi dung log gia ban
        if features["discount_rate"].notna().sum() < 5:
            features = features[["log_sale_price"]]

        # Dien cac gia tri thieu bang trung vi cua nhom
        features = features.fillna(features.median())

        detector = IsolationForest(
            n_estimators=200,
            contamination=CONTAMINATION,
            random_state=42
        )

        predictions = detector.fit_predict(features)
        scores = detector.decision_function(features)

        df.loc[group.index, "anomaly_label"] = np.where(
            predictions == -1,
            "Gia co dau hieu bat thuong",
            "Gia binh thuong"
        )

        df.loc[group.index, "anomaly_score"] = scores

    # 6. Tong hop ket qua
    print("\n=== KET QUA PHAT HIEN ===")
    print(df["anomaly_label"].value_counts().to_string())

    print("\n=== SO SANH THEO DANH MUC ===")
    summary = (
        df.groupby("category_name", dropna=False)
        .agg(
            so_san_pham=("sale_price_vnd", "size"),
            so_gia_bat_thuong=(
                "anomaly_label",
                lambda s: (s == "Gia co dau hieu bat thuong").sum()
            ),
            gia_trung_vi=("sale_price_vnd", "median")
        )
        .sort_values("so_gia_bat_thuong", ascending=False)
    )

    print(summary.to_string())

    # 7. Xuat cac san pham co dau hieu bat thuong
    anomalies = df[
        df["anomaly_label"] == "Gia co dau hieu bat thuong"
    ].copy()

    anomalies = anomalies.sort_values(
        "anomaly_score", ascending=True
    )

    output_columns = [
        "listing_id",
        "name",
        "brand_name",
        "category_name",
        "retailer_name",
        "sale_price_vnd",
        "list_price_vnd",
        "anomaly_score",
        "product_url"
    ]

    output_columns = [
        col for col in output_columns if col in anomalies.columns
    ]

    os.makedirs("results", exist_ok=True)

    output_path = "results/price_anomalies.csv"
    anomalies[output_columns].to_csv(
        output_path,
        index=False,
        encoding="utf-8-sig"
    )

    # Luu toan bo ket qua de giao dien web su dung
    all_results_path = "results/isolation_forest_results.csv"

    df.to_csv(
        all_results_path,
        index=False,
        encoding="utf-8-sig"
    )

    print("\n=== MOT SO SAN PHAM CAN KIEM TRA ===")
    if len(anomalies) > 0:
        print(
            anomalies[output_columns]
            .head(15)
            .to_string(index=False)
        )
    else:
        print("Khong tim thay san pham bat thuong.")

    print("\nDa luu danh sach bat thuong:", output_path)
    print("Da luu toan bo ket qua:", all_results_path)
    print(
        "\nLuu y: Gia bat thuong la dau hieu can kiem tra, "
        "khong khang dinh gia sai."
    )

    # 8. Cap nhat ket qua Isolation Forest vao MongoDB Atlas
    print("\n=== CAP NHAT KET QUA VAO MONGODB ===")

    operations = []

    for _, row in df.iterrows():
        listing_id = row.get("listing_id")

        if pd.isna(listing_id):
            continue

        update_fields = {
            "anomaly_label": str(row["anomaly_label"])
        }

        if pd.notna(row["anomaly_score"]):
            update_fields["anomaly_score"] = float(
                row["anomaly_score"]
            )

        operations.append(
            UpdateOne(
                {"listing_id": listing_id},
                {"$set": update_fields}
            )
        )

    if operations:
        result = products.bulk_write(
            operations,
            ordered=False
        )

        print("So ban ghi khop:", result.matched_count)
        print("So ban ghi thay doi:", result.modified_count)

    print(
        "Tong san pham co nhan anomaly_label:",
        products.count_documents(
            {"anomaly_label": {"$exists": True}}
        )
    )



if __name__ == "__main__":
    main()
