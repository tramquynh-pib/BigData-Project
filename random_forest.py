
import os
import pandas as pd
import joblib

from sklearn.model_selection import train_test_split
from sklearn.compose import ColumnTransformer
from sklearn.preprocessing import OneHotEncoder, StandardScaler
from sklearn.impute import SimpleImputer
from sklearn.pipeline import Pipeline
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    classification_report,
    confusion_matrix,
    f1_score
)

from database import products


# 1. Doc du lieu tu MongoDB
documents = list(products.find({}, {"_id": 0}))
df = pd.json_normalize(documents)

print("=" * 60)
print("MO HINH RANDOM FOREST - PHAN LOAI PHAN KHUC GIA")
print("=" * 60)
print("So san pham ban dau:", len(df))


# 2. Chuan hoa du lieu
df["sale_price_vnd"] = pd.to_numeric(
    df["sale_price_vnd"], errors="coerce"
)

numeric_features = [
    "quantity_sold",
    "rating",
    "review_count"
]

categorical_features = [
    "brand.brand",
    "category.category_context",
    "retailer.source"
]

for col in numeric_features:
    if col in df.columns:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    else:
        df[col] = float("nan")

for col in categorical_features:
    if col not in df.columns:
        df[col] = "Khong ro"
    else:
        df[col] = df[col].fillna("Khong ro").astype(str)

df = df.dropna(subset=["sale_price_vnd"])
df = df[df["sale_price_vnd"] > 0].copy()


# 3. Tao nhan phan khuc gia
bins = [
    0,
    5_000_000,
    15_000_000,
    30_000_000,
    float("inf")
]

labels = [
    "Gia thap",
    "Gia trung binh",
    "Gia cao",
    "Cao cap"
]

df["price_segment"] = pd.cut(
    df["sale_price_vnd"],
    bins=bins,
    labels=labels,
    right=False
)

df = df.dropna(subset=["price_segment"]).copy()

print("\nPhan bo phan khuc gia:")
print(df["price_segment"].value_counts().reindex(labels))


# 4. Chon dac trung va bien muc tieu
# Khong dua gia ban vao dau vao vi day la bien tao nhan.
# Khong dung list_price_vnd de han che ro ri thong tin gia.
feature_columns = numeric_features + categorical_features

X = df[feature_columns]
y = df["price_segment"].astype(str)


# 5. Chia du lieu huan luyen va kiem tra
X_train, X_test, y_train, y_test = train_test_split(
    X,
    y,
    test_size=0.2,
    random_state=42,
    stratify=y
)


# 6. Tien xu ly du lieu
numeric_pipeline = Pipeline([
    ("imputer", SimpleImputer(strategy="median")),
    ("scaler", StandardScaler())
])

categorical_pipeline = Pipeline([
    ("imputer", SimpleImputer(strategy="most_frequent")),
    ("encoder", OneHotEncoder(handle_unknown="ignore"))
])

preprocessor = ColumnTransformer([
    ("numeric", numeric_pipeline, numeric_features),
    ("categorical", categorical_pipeline, categorical_features)
])


# 7. Xay dung Random Forest
model = Pipeline([
    ("preprocessor", preprocessor),
    ("classifier", RandomForestClassifier(
        n_estimators=300,
        class_weight="balanced",
        random_state=42,
        min_samples_leaf=2,
        n_jobs=-1
    ))
])


# 8. Huan luyen mo hinh
print("\nDang huan luyen mo hinh...")
model.fit(X_train, y_train)

y_pred = model.predict(X_test)


# 9. Danh gia mo hinh
accuracy = accuracy_score(y_test, y_pred)
macro_f1 = f1_score(
    y_test, y_pred, average="macro", zero_division=0
)
weighted_f1 = f1_score(
    y_test, y_pred, average="weighted", zero_division=0
)

print("\n" + "=" * 60)
print("KET QUA DANH GIA")
print("=" * 60)
print(f"Accuracy:     {accuracy:.4f}")
print(f"Macro F1:     {macro_f1:.4f}")
print(f"Weighted F1:  {weighted_f1:.4f}")

print("\nBao cao phan loai:")
print(classification_report(
    y_test,
    y_pred,
    labels=labels,
    zero_division=0
))

print("Ma tran nham lan:")
print(pd.DataFrame(
    confusion_matrix(y_test, y_pred, labels=labels),
    index=[f"Thuc te: {x}" for x in labels],
    columns=[f"Du doan: {x}" for x in labels]
))


# 10. Luu mo hinh
os.makedirs("models", exist_ok=True)
model_path = os.path.join("models", "random_forest_price.joblib")
joblib.dump(model, model_path)

print("\nDa luu mo hinh tai:", model_path)
print("Hoan tat!")
