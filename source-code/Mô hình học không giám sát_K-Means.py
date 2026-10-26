
import pandas as pd
import matplotlib.pyplot as plt

from sklearn.preprocessing import StandardScaler
from sklearn.cluster import KMeans
from sklearn.metrics import silhouette_score

df = pd.read_csv("products_clean.csv")

print("Số dòng, số cột:", df.shape)

# CHỌN ĐẶC TRƯNG PHÂN CỤM
# Chỉ chọn các biến số để phân tích thị trường
candidate_features = [
    "sale_price_vnd",
    "discount_percent",
    "quantity_sold",
    "rating",
    "review_count"
]

# Giữ các cột có trong file dữ liệu
features = [
    col for col in candidate_features
    if col in df.columns
]

if len(features) < 2:
    raise ValueError("Không đủ đặc trưng để phân cụm.")

X = df[features].copy()

print("\nCác đặc trưng được chọn:", features)

# KIỂM TRA DỮ LIỆU ĐẦU VÀO
# Đảm bảo các đặc trưng có dạng số
X = X.apply(pd.to_numeric, errors="coerce")

# Thay giá trị vô hạn bằng giá trị thiếu để kiểm tra
X = X.replace([float("inf"), float("-inf")], float("nan"))

print("\nSố giá trị thiếu:")
print(X.isnull().sum())

# Dừng để kiểm tra nếu dữ liệu đầu vào chưa đạt yêu cầu
if X.isnull().any().any():
    raise ValueError(
        "Các cột dùng cho K-Means còn giá trị thiếu. "
        "Hãy kiểm tra lại file đã làm sạch."
    )

# Bỏ cột không thay đổi vì không giúp phân biệt các cụm
features = [
    col for col in X.columns
    if X[col].nunique() > 1
]
X = X[features]

if len(features) < 2:
    raise ValueError(
        "Cần ít nhất 2 đặc trưng có sự thay đổi."
    )

print("\nSố sản phẩm đưa vào mô hình:", len(X))
print("Đặc trưng sử dụng:", features)

# CHUẨN HÓA DỮ LIỆU
scaler = StandardScaler()
X_scaled = scaler.fit_transform(X)

# ĐÁNH GIÁ SỐ CỤM K
# Elbow Method và Silhouette Score
# Thử K từ 2 đến 8
max_k = min(8, len(X) - 1)

if max_k < 2:
    raise ValueError("Không đủ sản phẩm để phân cụm.")

k_values = list(range(2, max_k + 1))
inertias = []
silhouette_scores = []

for k in k_values:

    model = KMeans(
        n_clusters=k,
        random_state=42,
        n_init=10
    )

    labels = model.fit_predict(X_scaled)

    inertias.append(model.inertia_)
    silhouette_scores.append(
        silhouette_score(X_scaled, labels)
    )
# Vẽ biểu đồ Elbow
plt.figure(figsize=(8, 5))
plt.plot(k_values, inertias, marker="o")
plt.title("Elbow Method - Chọn số cụm K")
plt.xlabel("Số cụm K")
plt.ylabel("Inertia")
plt.xticks(k_values)
plt.grid(True)
plt.tight_layout()
plt.show()


# Vẽ biểu đồ Silhouette
plt.figure(figsize=(8, 5))
plt.plot(k_values, silhouette_scores, marker="o")
plt.title("Silhouette Score - Đánh giá phân cụm")
plt.xlabel("Số cụm K")
plt.ylabel("Silhouette Score")
plt.xticks(k_values)
plt.grid(True)
plt.tight_layout()
plt.show()
# In bảng kết quả để so sánh
evaluation = pd.DataFrame({
    "K": k_values,
    "Inertia": inertias,
    "Silhouette Score": silhouette_scores
})

print("\nBẢNG ĐÁNH GIÁ SỐ CỤM:")
print(evaluation.round(4).to_string(index=False))

# CHỌN K VÀ HUẤN LUYỆN K-MEANS
# Dùng Silhouette cao nhất làm gợi ý,
# sau đó đối chiếu với biểu đồ Elbow.
best_index = silhouette_scores.index(
    max(silhouette_scores)
)

K_FINAL = k_values[best_index]

print("\nK được gợi ý theo Silhouette:", K_FINAL)
print("Hãy đối chiếu thêm với điểm gấp khúc Elbow.")

kmeans = KMeans(
    n_clusters=K_FINAL,
    random_state=42,
    n_init=10
)

cluster_labels = kmeans.fit_predict(X_scaled)

# Gắn nhãn cụm vào bản ghi tương ứng
df_result = df.loc[X.index].copy()
df_result["cluster"] = cluster_labels

print("\nĐã hoàn thành phân cụm.")
print("Silhouette Score của mô hình:",
      round(max(silhouette_scores), 4))


# PHÂN TÍCH ĐẶC ĐIỂM TỪNG CỤM
# Thống kê số sản phẩm và giá trị trung bình
summary = df_result.groupby("cluster").agg(
    so_san_pham=("cluster", "size"),
    **{
        col: (col, "mean")
        for col in features
    }
).round(2)

print("\nĐẶC ĐIỂM CÁC CỤM:")
print(summary.to_string())
# Thống kê số sản phẩm theo cụm
print("\nSỐ SẢN PHẨM TRONG MỖI CỤM:")
print(
    df_result["cluster"]
    .value_counts()
    .sort_index()
)
# LƯU KẾT QUẢ

df_result.to_csv(
    "products_kmeans_result.csv",
    index=False,
    encoding="utf-8-sig"
)

summary.to_csv(
    "kmeans_cluster_summary.csv",
    encoding="utf-8-sig"
)

evaluation.to_csv(
    "kmeans_evaluation.csv",
    index=False,
    encoding="utf-8-sig"
)

print("\nĐã lưu 3 file kết quả:")
print("1. products_kmeans_result.csv")
print("2. kmeans_cluster_summary.csv")
print("3. kmeans_evaluation.csv")
