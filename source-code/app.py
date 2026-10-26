# 2.4.4 Giao diện và 2.4.5 Phân quyền
import os
import re
from datetime import timedelta
from pathlib import Path
from functools import wraps

import joblib
import numpy as np
import pandas as pd
from flask import (
    Flask, abort, flash, redirect, render_template, request,
    session, url_for
)
from jinja2 import DictLoader
from werkzeug.security import check_password_hash, generate_password_hash

from config import OUT
from database import db, products as product_collection

# ---------------------------------------------------------
# CẤU HÌNH
# ---------------------------------------------------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "doi-khoa-bi-mat-truoc-khi-nop")
app.permanent_session_lifetime = timedelta(hours=2)

ROLES = ["admin", "user"]
SEGMENTS = ["Gia thap", "Gia trung binh", "Gia cao", "Cao cap"]
PAGE_SIZE = 25
BASE_DIR = Path(__file__).resolve().parent
MODEL_PATH = BASE_DIR / "models" / "random_forest_price.joblib"
POWERBI_URL = os.environ.get("POWERBI_URL", "")

# Các ngưỡng này khớp với random_forest.py
PRICE_BINS = [0, 5_000_000, 15_000_000, 30_000_000, float("inf")]


# ---------------------------------------------------------
# CHUẨN HÓA DOCUMENT MONGODB
# Dữ liệu gốc có brand.brand, category.category_context,
# retailer.source; giao diện dùng tên trường phẳng.
# ---------------------------------------------------------
def normalize_product(doc):
    p = dict(doc)
    brand_obj = p.get("brand")
    category_obj = p.get("category")
    retailer_obj = p.get("retailer")

    if isinstance(brand_obj, dict):
        p["brand"] = brand_obj.get("brand") or "Khác"
    else:
        p["brand"] = brand_obj or "Khác"

    if isinstance(category_obj, dict):
        p["category_context"] = (
            category_obj.get("category_context")
            or category_obj.get("category")
            or "Khác"
        )
    else:
        p["category_context"] = (
            p.get("category_context") or category_obj or "Khác"
        )

    if isinstance(retailer_obj, dict):
        p["source"] = retailer_obj.get("source") or "Không rõ"
    else:
        p["source"] = p.get("source") or "Không rõ"

    p["name"] = p.get("name") or "Chưa có tên"
    p["listing_id"] = str(p.get("listing_id") or p.get("product_url") or "")
    p["sale_price_vnd"] = pd.to_numeric(
        p.get("sale_price_vnd"), errors="coerce"
    )
    p["list_price_vnd"] = pd.to_numeric(
        p.get("list_price_vnd"), errors="coerce"
    )
    p["quantity_sold"] = pd.to_numeric(p.get("quantity_sold"), errors="coerce")
    p["rating"] = pd.to_numeric(p.get("rating"), errors="coerce")
    p["review_count"] = pd.to_numeric(p.get("review_count"), errors="coerce")

    if p.get("discount_percent") is None:
        sale = p["sale_price_vnd"]
        listed = p["list_price_vnd"]
        if pd.notna(sale) and pd.notna(listed) and listed > 0:
            p["discount_percent"] = max(0.0, (listed - sale) / listed * 100)
        else:
            p["discount_percent"] = 0.0
    else:
        p["discount_percent"] = pd.to_numeric(
            p.get("discount_percent"), errors="coerce"
        )
        if pd.isna(p["discount_percent"]):
            p["discount_percent"] = 0.0

    # Tạo phân khúc hiển thị nếu document chưa được gắn nhãn.
    if not p.get("price_segment") and pd.notna(p["sale_price_vnd"]):
        price = p["sale_price_vnd"]
        if price < 5_000_000:
            p["price_segment"] = "Gia thap"
        elif price < 15_000_000:
            p["price_segment"] = "Gia trung binh"
        elif price < 30_000_000:
            p["price_segment"] = "Gia cao"
        else:
            p["price_segment"] = "Cao cap"

    p.setdefault("cluster", None)
    p.setdefault("is_anomaly", False)
    p.setdefault("anomaly_score", None)
    p.setdefault("price_ratio_vs_median", None)
    p.setdefault("anomaly_reason", "")
    p.setdefault("product_url", "")
    return p


def get_all_products():
    """Đọc collection Atlas đang được khai báo trong database.py."""
    docs = list(product_collection.find({}, {"_id": 0}))
    return [normalize_product(d) for d in docs]


def get_product_options(field):
    values = {
        str(p.get(field))
        for p in get_all_products()
        if p.get(field) not in (None, "")
    }
    return sorted(values, key=str.casefold)


# ---------------------------------------------------------
# PHÂN QUYỀN
# ---------------------------------------------------------
def login_required(roles=None):
    def deco(func):
        @wraps(func)
        def wrapper(*args, **kwargs):
            if "user" not in session:
                return redirect(url_for("login", next=request.path))
            if roles and session.get("role") not in roles:
                abort(403)
            return func(*args, **kwargs)
        return wrapper
    return deco


@app.context_processor
def inject_user():
    return {"user": session.get("user"), "role": session.get("role")}


@app.template_filter("vnd")
def vnd(value):
    try:
        if value is None or pd.isna(value):
            return "-"
        return f"{int(float(value)):,}".replace(",", ".") + " đ"
    except (TypeError, ValueError, OverflowError):
        return "-"


@app.errorhandler(403)
def forbidden(_error):
    return render_template("403.html"), 403


def seed_users():
    """Tạo tài khoản mẫu nếu collection users chưa có tài khoản."""
    db.users.create_index("username", unique=True)
    if db.users.count_documents({}) == 0:
        db.users.insert_many([
            {
                "username": "admin",
                "password_hash": generate_password_hash("admin123"),
                "role": "admin",
            },
            {
                "username": "user",
                "password_hash": generate_password_hash("user123"),
                "role": "user",
            },
        ])
        print(
            "Đã tạo tài khoản mẫu admin/admin123 và user/user123. "
            "Hãy đổi mật khẩu trước khi nộp."
        )


# ---------------------------------------------------------
# ĐĂNG NHẬP / ĐĂNG XUẤT
# ---------------------------------------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        user_doc = db.users.find_one({"username": username})

        if user_doc and check_password_hash(
            user_doc.get("password_hash", ""), password
        ):
            session.clear()
            session.permanent = True
            session["user"] = user_doc["username"]
            session["role"] = user_doc.get("role", "user")

            next_url = request.args.get("next", "/")
            if next_url.startswith("/") and not next_url.startswith("//"):
                return redirect(next_url)
            return redirect(url_for("dashboard"))

        flash("Sai tên đăng nhập hoặc mật khẩu.")
    return render_template("login.html")


@app.route("/logout", methods=["GET"])
def logout():
    session.clear()
    return redirect(url_for("login"))


# ---------------------------------------------------------
# DASHBOARD
# ---------------------------------------------------------
@app.route("/")
@login_required()
def dashboard():
    try:
        docs = get_all_products()
    except Exception:
        app.logger.exception("Không đọc được dữ liệu sản phẩm từ MongoDB")
        return render_template(
            "dashboard.html", empty=True, powerbi=POWERBI_URL,
            error="Không đọc được dữ liệu từ MongoDB. Hãy kiểm tra kết nối Atlas."
        )

    df = pd.DataFrame(docs)
    if df.empty:
        return render_template(
            "dashboard.html", empty=True, powerbi=POWERBI_URL, error=None
        )

    def counts(column, top=None):
        if column not in df.columns:
            return {"labels": [], "data": []}
        series = df[column].fillna("Khác").astype(str).value_counts()
        if top:
            series = series.head(top)
        return {
            "labels": [str(x) for x in series.index],
            "data": [int(x) for x in series.values],
        }

    prices = pd.to_numeric(df.get("sale_price_vnd"), errors="coerce")
    discounts = pd.to_numeric(
        df.get("discount_percent", pd.Series(0, index=df.index)),
        errors="coerce"
    ).fillna(0)
    brands = df.get("brand", pd.Series("Khác", index=df.index)).fillna("Khác")

    kpi = {
        "Tổng sản phẩm": f"{len(df):,}",
        "Số thương hiệu": int(brands.nunique()),
        "Giá trung bình": vnd(prices.mean()),
        "Giá trung vị": vnd(prices.median()),
        "% có giảm giá": f"{(discounts > 0).mean() * 100:.1f}%",
    }
    if "is_anomaly" in df.columns:
        anomaly_flags = df["is_anomaly"].fillna(False).astype(bool)
        kpi["Ứng viên giá bất thường"] = int(anomaly_flags.sum())

    return render_template(
        "dashboard.html",
        empty=False,
        error=None,
        kpi=kpi,
        powerbi=POWERBI_URL,
        by_cat=counts("category_context"),
        by_seg=counts("price_segment"),
        by_src=counts("source"),
        by_brand=counts("brand", 12),
    )


# ---------------------------------------------------------
# DANH SÁCH SẢN PHẨM: TÌM KIẾM / LỌC / PHÂN TRANG
# ---------------------------------------------------------
@app.route("/products")
@login_required()
def products_page():
    args = request.args
    all_rows = get_all_products()
    q_text = args.get("q", "").strip()
    brand_filter = args.get("brand", "")
    category_filter = args.get("category_context", "")
    source_filter = args.get("source", "")
    segment_filter = args.get("price_segment", "")

    min_price = max_price = None
    try:
        if args.get("min_price", "").strip():
            min_price = float(args["min_price"])
        if args.get("max_price", "").strip():
            max_price = float(args["max_price"])
        if min_price is not None and max_price is not None and min_price > max_price:
            flash("Giá tối thiểu không được lớn hơn giá tối đa.")
            min_price = max_price = None
    except ValueError:
        flash("Khoảng giá phải là số.")
        min_price = max_price = None

    rows = []
    for product in all_rows:
        if q_text and q_text.casefold() not in str(product.get("name", "")).casefold():
            continue
        if brand_filter and product.get("brand") != brand_filter:
            continue
        if category_filter and product.get("category_context") != category_filter:
            continue
        if source_filter and product.get("source") != source_filter:
            continue
        if segment_filter and product.get("price_segment") != segment_filter:
            continue

        price = product.get("sale_price_vnd")
        if min_price is not None and (pd.isna(price) or price < min_price):
            continue
        if max_price is not None and (pd.isna(price) or price > max_price):
            continue
        rows.append(product)

    sort_key = args.get("sort", "name")
    sort_map = {
        "price_asc": ("sale_price_vnd", False),
        "price_desc": ("sale_price_vnd", True),
        "sold_desc": ("quantity_sold", True),
        "name": ("name", False),
    }
    field, reverse = sort_map.get(sort_key, ("name", False))
    rows.sort(
        key=lambda p: (
            p.get(field) is None or (
                isinstance(p.get(field), float) and pd.isna(p.get(field))
            ),
            str(p.get(field, "")).casefold()
            if field == "name"
            else (float(p[field]) if pd.notna(p.get(field)) else 0),
        ),
        reverse=reverse,
    )

    total = len(rows)
    page = max(args.get("page", 1, type=int), 1)
    pages = max((total + PAGE_SIZE - 1) // PAGE_SIZE, 1)
    page = min(page, pages)
    page_rows = rows[(page - 1) * PAGE_SIZE: page * PAGE_SIZE]
    query_string = {k: v for k, v in args.items() if k != "page"}

    return render_template(
        "products.html",
        rows=page_rows,
        total=total,
        page=page,
        pages=pages,
        qs=query_string,
        brands=get_product_options("brand"),
        categories=get_product_options("category_context"),
        sources=get_product_options("source"),
        segments=SEGMENTS,
    )


@app.route("/admin/products/<path:lid>/delete", methods=["POST"])
@login_required(["admin"])
def delete_product(lid):
    result = product_collection.delete_one({"listing_id": lid})
    if result.deleted_count:
        flash("Đã xóa sản phẩm.")
    else:
        flash("Không tìm thấy sản phẩm để xóa.")
    return redirect(request.referrer or url_for("products_page"))


# ---------------------------------------------------------
# K-MEANS
# Chỉ hiển thị kết quả nếu collection đã có trường cluster.
# ---------------------------------------------------------
@app.route("/clusters")
@login_required()
def clusters():
    docs = [p for p in get_all_products() if p.get("cluster") is not None]
    if not docs:
        return render_template("clusters.html", summary=None)

    df = pd.DataFrame(docs)
    df["cluster"] = pd.to_numeric(df["cluster"], errors="coerce")
    df = df.dropna(subset=["cluster"])
    if df.empty:
        return render_template("clusters.html", summary=None)

    summary = []
    for cluster_id, group in df.groupby("cluster"):
        prices = pd.to_numeric(group["sale_price_vnd"], errors="coerce")
        discounts = pd.to_numeric(group["discount_percent"], errors="coerce")
        sold = pd.to_numeric(group["quantity_sold"], errors="coerce")
        ratings = pd.to_numeric(group["rating"], errors="coerce")
        brand_names = group["brand"].fillna("Khác").astype(str).value_counts().head(3).index
        summary.append({
            "cluster": int(cluster_id),
            "so_sp": int(len(group)),
            "gia_tb": prices.mean(),
            "gia_trung_vi": prices.median(),
            "giam_gia": discounts.mean(),
            "da_ban_tv": sold.median(),
            "rating": ratings.mean(),
            "hang": ", ".join(brand_names),
        })

    selected = request.args.get("c", type=int)
    items = [
        p for p in docs
        if selected is not None and pd.to_numeric(p.get("cluster"), errors="coerce") == selected
    ][:100]

    return render_template(
        "clusters.html",
        summary=summary,
        sel=selected,
        items=items,
        chart={
            "labels": [f"Cụm {row['cluster']}" for row in summary],
            "data": [row["so_sp"] for row in summary],
        },
    )


# ---------------------------------------------------------
# RANDOM FOREST: MÔ HÌNH ĐƯỢC LƯU TRỰC TIẾP DƯỚI DẠNG PIPELINE
# Cột phải khớp random_forest.py.
# ---------------------------------------------------------
@app.route("/predict", methods=["GET", "POST"])
@login_required()
def predict():
    if not MODEL_PATH.exists():
        return render_template("predict.html", missing=True)

    try:
        model = joblib.load(MODEL_PATH)
    except Exception:
        app.logger.exception("Không tải được mô hình Random Forest")
        flash("Không tải được mô hình. Hãy kiểm tra file model.")
        return render_template("predict.html", missing=True)

    result = None
    form = request.form if request.method == "POST" else {}

    if request.method == "POST":
        try:
            def numeric_value(key):
                value = request.form.get(key, "").strip()
                return float(value) if value else np.nan

            row = {
                "quantity_sold": numeric_value("quantity_sold"),
                "rating": numeric_value("rating"),
                "review_count": numeric_value("review_count"),
                "brand.brand": request.form.get("brand", "Khác"),
                "category.category_context": request.form.get("category_context", "Khác"),
                "retailer.source": request.form.get("source", "Không rõ"),
            }
            feature_columns = [
                "quantity_sold", "rating", "review_count",
                "brand.brand", "category.category_context", "retailer.source",
            ]
            X = pd.DataFrame([row], columns=feature_columns)
            probabilities = model.predict_proba(X)[0]
            result = sorted(
                zip(model.classes_, probabilities),
                key=lambda pair: pair[1],
                reverse=True,
            )
        except (ValueError, TypeError, KeyError) as error:
            app.logger.warning("Lỗi dự đoán: %s", error)
            flash("Không thể dự đoán với dữ liệu vừa nhập. Hãy kiểm tra các ô số.")
        except Exception:
            app.logger.exception("Lỗi khi chạy dự đoán")
            flash("Mô hình không tương thích với dữ liệu đầu vào.")

    return render_template(
        "predict.html",
        missing=False,
        result=result,
        form=form,
        brands=get_product_options("brand"),
        categories=get_product_options("category_context"),
        sources=get_product_options("source"),
    )


# ---------------------------------------------------------
# PHÁT HIỆN GIÁ BẤT THƯỜNG
# Trang này hiển thị những document đã có is_anomaly=True.
# Nếu chưa nạp kết quả Isolation Forest vào Atlas, bảng sẽ trống.
# ---------------------------------------------------------

@app.route("/anomalies")
@login_required()
def anomalies():
    docs = get_all_products()
    cat = request.args.get("category_context", "")

    # Chuyển các trường dữ liệu lồng nhau về đúng tên mà giao diện sử dụng
    normalized_docs = []

    for p in docs:
        category = p.get("category") or {}
        retailer = p.get("retailer") or {}

        if not isinstance(category, dict):
            category = {}
        if not isinstance(retailer, dict):
            retailer = {}

        item = dict(p)
        item["category_context"] = (
            p.get("category_context")
            or category.get("category_context")
            or ""
        )
        item["source"] = (
            p.get("source")
            or retailer.get("source")
            or ""
        )

        # Tương thích với kết quả Isolation Forest đã lưu trên Atlas
        label = p.get("anomaly_label", "")
        item["is_anomaly"] = (
            p.get("is_anomaly") is True
            or label == "Gia co dau hieu bat thuong"
        )

        # Hiện tại script chưa lưu hai trường này
        item.setdefault("price_ratio_vs_median", None)
        item.setdefault("anomaly_reason", label or "")

        normalized_docs.append(item)

    rows = [
        p for p in normalized_docs
        if p.get("is_anomaly")
        and (not cat or p.get("category_context") == cat)
    ]

    rows.sort(
        key=lambda p: (
            p.get("anomaly_score") is None,
            float(p.get("anomaly_score") or 0),
        )
    )

    cats = sorted({
        str(p.get("category_context"))
        for p in normalized_docs
        if p.get("is_anomaly") and p.get("category_context")
    })

    return render_template(
        "anomalies.html",
        rows=rows[:200],
        cats=cats,
        cat=cat
    )


# ---------------------------------------------------------
# QUẢN LÝ NGƯỜI DÙNG: CHỈ ADMIN
# ---------------------------------------------------------
@app.route("/admin/users")
@login_required(["admin"])
def users():
    safe_users = list(
        db.users.find({}, {"_id": 0, "password_hash": 0}).sort("username", 1)
    )
    return render_template("users.html", users=safe_users, roles=ROLES)


@app.route("/admin/users/create", methods=["POST"])
@login_required(["admin"])
def create_user():
    name = request.form.get("username", "").strip()
    password = request.form.get("password", "")
    role = request.form.get("role", "")

    if not re.fullmatch(r"[A-Za-z0-9_.-]{3,30}", name) or len(password) < 6 or role not in ROLES:
        flash("Tên đăng nhập 3–30 ký tự (chữ, số, _ . -), mật khẩu tối thiểu 6 ký tự và vai trò hợp lệ.")
    elif db.users.find_one({"username": name}):
        flash("Tên đăng nhập đã tồn tại.")
    else:
        try:
            db.users.insert_one({
                "username": name,
                "password_hash": generate_password_hash(password),
                "role": role,
            })
            flash(f"Đã tạo tài khoản {name}.")
        except Exception:
            app.logger.exception("Không tạo được tài khoản")
            flash("Không tạo được tài khoản. Hãy kiểm tra dữ liệu và kết nối.")
    return redirect(url_for("users"))


@app.route("/admin/users/<name>/role", methods=["POST"])
@login_required(["admin"])
def change_role(name):
    role = request.form.get("role", "")
    if name == session.get("user"):
        flash("Không thể tự đổi vai trò của chính mình.")
    elif role not in ROLES:
        flash("Vai trò không hợp lệ.")
    else:
        result = db.users.update_one(
            {"username": name}, {"$set": {"role": role}}
        )
        flash("Đã cập nhật vai trò." if result.matched_count else "Không tìm thấy tài khoản.")
    return redirect(url_for("users"))


@app.route("/admin/users/<name>/delete", methods=["POST"])
@login_required(["admin"])
def delete_user(name):
    if name == session.get("user"):
        flash("Không thể tự xóa tài khoản đang đăng nhập.")
    else:
        result = db.users.delete_one({"username": name})
        flash("Đã xóa tài khoản." if result.deleted_count else "Không tìm thấy tài khoản.")
    return redirect(url_for("users"))


# ---------------------------------------------------------
# GIAO DIỆN HTML NHÚNG TRONG FILE
# ---------------------------------------------------------
T = {}

T["base.html"] = """<!doctype html><html lang="vi"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Phân tích thị trường công nghệ</title>
<style>
*{box-sizing:border-box}body{font-family:system-ui,Arial,sans-serif;margin:0;background:#f4f6f8;color:#222}
nav{background:#1f2d3d;padding:12px 20px;display:flex;gap:16px;align-items:center;flex-wrap:wrap}
nav a{color:#dfe7ef;text-decoration:none}nav a:hover{text-decoration:underline}nav .sp{flex:1}nav span{color:#9fb3c8}
main{max-width:1200px;margin:20px auto;padding:0 16px}.card{background:#fff;border-radius:8px;padding:16px;margin-bottom:16px;box-shadow:0 1px 3px #0002}
.kpis{display:grid;grid-template-columns:repeat(auto-fit,minmax(170px,1fr));gap:12px}.kpis b{display:block;font-size:1.4em;margin-top:5px}
table{border-collapse:collapse;width:100%;font-size:14px}th,td{border-bottom:1px solid #e3e7eb;padding:8px;text-align:left;vertical-align:top}
th{background:#eef2f6}input,select,button{padding:8px;margin:3px;max-width:100%}button{cursor:pointer}

.flash{padding:10px 12px;border-radius:6px;background:#fff3cd;margin-bottom:10px}


.grid2{
    display:grid;
    grid-template-columns:repeat(2,minmax(0,1fr));
    gap:20px;
    align-items:stretch;
}

.grid2 > .card{
    min-width:0;
    width:100%;
    margin-bottom:0;
}

.grid2 > .card canvas{
    display:block;
    width:100% !important;
    height:280px !important;
}

@media(max-width:768px){
    .grid2{
        grid-template-columns:1fr;
    }

    .grid2 > .card canvas{
        height:250px !important;
    }
}


.tag{padding:2px 8px;border-radius:10px;background:#e8eef5;font-size:12px}.bad{background:#fde2e2}
.table-wrap{overflow-x:auto}.muted{color:#687786}
</style><script src="https://cdnjs.cloudflare.com/ajax/libs/Chart.js/4.4.1/chart.umd.min.js"></script>
<script>function bar(id,l,d,t){const e=document.getElementById(id);if(e)new Chart(e,{type:'bar',data:{labels:l,datasets:[{label:t,data:d}]},options:{responsive:true,plugins:{legend:{display:false}}}});}</script>
</head><body>{% if user %}<nav><a href="/">Dashboard</a><a href="/products">Sản phẩm</a><a href="/clusters">Phân khúc K-Means</a>
<a href="/predict">Dự đoán phân khúc giá</a><a href="/anomalies">Giá bất thường</a>
{% if role=='admin' %}<a href="/admin/users">Quản lý người dùng</a>{% endif %}
<div class="sp"></div><span>{{user}} ({{role}})</span><a href="/logout">Đăng xuất</a></nav>{% endif %}
<main>{% for m in get_flashed_messages() %}<div class="flash">{{m}}</div>{% endfor %}{% block body %}{% endblock %}</main></body></html>"""

T["login.html"] = """{% extends 'base.html' %}{% block body %}
<div class="card" style="max-width:380px;margin:60px auto"><h3>Đăng nhập hệ thống</h3>
<form method="post"><input name="username" placeholder="Tên đăng nhập" required style="width:95%"><br>
<input name="password" type="password" placeholder="Mật khẩu" required style="width:95%"><br>
<button type="submit">Đăng nhập</button></form></div>{% endblock %}"""

T["403.html"] = """{% extends 'base.html' %}{% block body %}
<div class="card"><h3>403 - Không đủ quyền</h3><p>Chức năng này chỉ dành cho quản trị viên (admin).</p><a href="/">Về trang chủ</a></div>
{% endblock %}"""

T["dashboard.html"] = """{% extends 'base.html' %}{% block body %}
{% if error %}<div class="card">{{error}}</div>{% endif %}
{% if empty %}<div class="card">Chưa có dữ liệu sản phẩm trong collection product_listings.</div>{% else %}
<div class="card kpis">{% for k,v in kpi.items() %}<div><span>{{k}}</span><b>{{v}}</b></div>{% endfor %}</div>
<div class="grid2"><div class="card"><h4>Số sản phẩm theo nhóm</h4><canvas id="c1"></canvas></div>
<div class="card"><h4>Phân khúc giá</h4><canvas id="c2"></canvas></div>
<div class="card"><h4>Số sản phẩm theo nguồn</h4><canvas id="c3"></canvas></div>
<div class="card"><h4>Top 12 thương hiệu</h4><canvas id="c4"></canvas></div></div>
<script>bar('c1',{{by_cat.labels|tojson}},{{by_cat.data|tojson}},'Sản phẩm');bar('c2',{{by_seg.labels|tojson}},{{by_seg.data|tojson}},'Sản phẩm');
bar('c3',{{by_src.labels|tojson}},{{by_src.data|tojson}},'Sản phẩm');bar('c4',{{by_brand.labels|tojson}},{{by_brand.data|tojson}},'Sản phẩm');</script>
{% endif %}{% if powerbi %}<div class="card"><h4>Dashboard Power BI</h4><iframe src="{{powerbi}}" width="100%" height="600" frameborder="0"></iframe></div>{% endif %}
{% endblock %}"""

T["products.html"] = """{% extends 'base.html' %}{% block body %}
<div class="card"><form method="get">
<input name="q" placeholder="Tìm theo tên" value="{{qs.get('q','')}}">
<select name="brand"><option value="">Tất cả hãng</option>{% for b in brands %}<option value="{{b}}" {{'selected' if qs.get('brand')==b else ''}}>{{b}}</option>{% endfor %}</select>
<select name="category_context"><option value="">Tất cả nhóm</option>{% for b in categories %}<option value="{{b}}" {{'selected' if qs.get('category_context')==b else ''}}>{{b}}</option>{% endfor %}</select>
<select name="source"><option value="">Tất cả nguồn</option>{% for b in sources %}<option value="{{b}}" {{'selected' if qs.get('source')==b else ''}}>{{b}}</option>{% endfor %}</select>
<select name="price_segment"><option value="">Tất cả phân khúc</option>{% for b in segments %}<option value="{{b}}" {{'selected' if qs.get('price_segment')==b else ''}}>{{b}}</option>{% endfor %}</select>
<input name="min_price" type="number" min="0" placeholder="Giá từ" value="{{qs.get('min_price','')}}" style="width:110px">
<input name="max_price" type="number" min="0" placeholder="Giá đến" value="{{qs.get('max_price','')}}" style="width:110px">
<select name="sort"><option value="name">Tên A-Z</option><option value="price_asc" {{'selected' if qs.get('sort')=='price_asc' else ''}}>Giá tăng</option>
<option value="price_desc" {{'selected' if qs.get('sort')=='price_desc' else ''}}>Giá giảm</option><option value="sold_desc" {{'selected' if qs.get('sort')=='sold_desc' else ''}}>Bán chạy</option></select>
<button type="submit">Lọc</button></form></div>
<div class="card"><p>{{total}} sản phẩm — trang {{page}}/{{pages}}</p><div class="table-wrap"><table>
<tr><th>Tên</th><th>Hãng</th><th>Nhóm</th><th>Nguồn</th><th>Giá bán</th><th>Phân khúc</th><th>Cụm</th><th>Trạng thái</th>{% if role=='admin' %}<th>Thao tác</th>{% endif %}</tr>
{% for p in rows %}<tr><td>{% if p.product_url %}<a href="{{p.product_url}}" target="_blank" rel="noopener noreferrer">{{p.name}}</a>{% else %}{{p.name}}{% endif %}</td>
<td>{{p.brand}}</td><td>{{p.category_context}}</td><td>{{p.source}}</td><td>{{p.sale_price_vnd|vnd}}</td><td>{{p.price_segment or ''}}</td><td>{{p.cluster if p.cluster is not none else ''}}</td>
<td>{% if p.is_anomaly %}<span class="tag bad">ứng viên bất thường</span>{% endif %}</td>
{% if role=='admin' %}<td><form method="post" action="{{url_for('delete_product',lid=p.listing_id)}}" onsubmit="return confirm('Xóa sản phẩm này?')"><button type="submit">Xóa</button></form></td>{% endif %}</tr>{% endfor %}
</table></div><p>{% if page>1 %}<a href="{{url_for('products_page',page=page-1,**qs)}}">« Trước</a>{% endif %}
{% if page<pages %}<a href="{{url_for('products_page',page=page+1,**qs)}}">Sau »</a>{% endif %}</p></div>{% endblock %}"""

T["clusters.html"] = """{% extends 'base.html' %}{% block body %}
{% if not summary %}<div class="card"><h4>Chưa có kết quả K-Means</h4><p>Collection hiện chưa có trường <code>cluster</code>. Trang này sẽ có dữ liệu sau khi kết quả phân cụm được ghép vào sản phẩm.</p></div>
{% else %}<div class="grid2"><div class="card"><h4>Số sản phẩm mỗi cụm</h4><canvas id="c1"></canvas></div>
<div class="card"><h4>Đặc điểm từng cụm</h4><div class="table-wrap"><table><tr><th>Cụm</th><th>Số SP</th><th>Giá TB</th><th>Giá trung vị</th><th>% giảm</th><th>Đã bán (TV)</th><th>Rating</th><th>Hãng phổ biến</th></tr>
{% for r in summary %}<tr><td><a href="/clusters?c={{r.cluster}}">Cụm {{r.cluster}}</a></td><td>{{r.so_sp}}</td><td>{{r.gia_tb|vnd}}</td><td>{{r.gia_trung_vi|vnd}}</td>
<td>{{'%.1f'|format(r.giam_gia or 0)}}%</td><td>{{r.da_ban_tv}}</td><td>{{r.rating}}</td><td>{{r.hang}}</td></tr>{% endfor %}</table></div></div></div>
{% if sel is not none %}<div class="card"><h4>Sản phẩm thuộc cụm {{sel}} (tối đa 100)</h4><div class="table-wrap"><table><tr><th>Tên</th><th>Hãng</th><th>Nhóm</th><th>Giá</th></tr>
{% for p in items %}<tr><td>{{p.name}}</td><td>{{p.brand}}</td><td>{{p.category_context}}</td><td>{{p.sale_price_vnd|vnd}}</td></tr>{% endfor %}</table></div></div>{% endif %}
<script>bar('c1',{{chart.labels|tojson}},{{chart.data|tojson}},'Sản phẩm');</script>{% endif %}{% endblock %}"""

T["predict.html"] = """{% extends 'base.html' %}{% block body %}
{% if missing %}<div class="card"><h4>Chưa có mô hình hoặc không tải được mô hình</h4><p>Kiểm tra file <code>models/random_forest_price.joblib</code> và chạy random_forest.py nếu chưa huấn luyện.</p></div>
{% else %}<div class="card"><h4>Dự đoán phân khúc giá — Random Forest</h4>
<p class="muted">Nhập thông tin bán hàng và đánh giá. Mô hình sử dụng số lượng bán, rating, số đánh giá, thương hiệu, nhóm sản phẩm và nguồn bán.</p>
<form method="post">
<label>Thương hiệu <select name="brand">{% for b in brands %}<option value="{{b}}" {{'selected' if form.get('brand')==b else ''}}>{{b}}</option>{% endfor %}</select></label>
<label>Nhóm sản phẩm <select name="category_context">{% for b in categories %}<option value="{{b}}" {{'selected' if form.get('category_context')==b else ''}}>{{b}}</option>{% endfor %}</select></label>
<label>Nguồn <select name="source">{% for b in sources %}<option value="{{b}}" {{'selected' if form.get('source')==b else ''}}>{{b}}</option>{% endfor %}</select></label><br>
{% for f,l in [('quantity_sold','Số lượng đã bán'),('rating','Rating (0–5)'),('review_count','Số lượt đánh giá')] %}
<label>{{l}} <input name="{{f}}" type="number" step="any" min="0" value="{{form.get(f,'')}}" placeholder="Để trống nếu chưa rõ"></label>
{% endfor %}<button type="submit">Dự đoán</button></form>
{% if result %}<h4>Phân khúc dự đoán: {{result[0][0]}}</h4><div class="table-wrap"><table><tr><th>Phân khúc</th><th>Xác suất mô hình</th></tr>
{% for c,p in result %}<tr><td>{{c}}</td><td>{{'%.1f'|format(p*100)}}%</td></tr>{% endfor %}</table></div><p class="muted">Xác suất là kết quả của mô hình, không phải cam kết về giá thực tế.</p>{% endif %}</div>{% endif %}{% endblock %}"""

T["anomalies.html"] = """{% extends 'base.html' %}{% block body %}
<div class="card"><h4>Sản phẩm có cờ giá bất thường</h4><form method="get">Nhóm:
<select name="category_context" onchange="this.form.submit()"><option value="">Tất cả</option>
{% for c in cats %}<option value="{{c}}" {{'selected' if cat==c else ''}}>{{c}}</option>{% endfor %}</select></form>
{% if not rows %}<p>Chưa có sản phẩm được gắn cờ bất thường trong collection Atlas. Cần ghép kết quả Isolation Forest vào dữ liệu trước khi trang này có thể hiển thị danh sách.</p>
{% else %}<div class="table-wrap"><table><tr><th>Tên</th><th>Nhóm</th><th>Nguồn</th><th>Giá bán</th><th>Giá / trung vị nhóm</th><th>Điểm</th><th>Lý do</th></tr>
{% for p in rows %}<tr><td>{% if p.product_url %}<a href="{{p.product_url}}" target="_blank" rel="noopener noreferrer">{{p.name}}</a>{% else %}{{p.name}}{% endif %}</td>
<td>{{p.category_context}}</td><td>{{p.source}}</td><td>{{p.sale_price_vnd|vnd}}</td><td>{{p.price_ratio_vs_median if p.price_ratio_vs_median is not none else '-'}}</td>
<td>{{p.anomaly_score if p.anomaly_score is not none else '-'}}</td><td>{{p.anomaly_reason or ''}}</td></tr>{% endfor %}</table></div>{% endif %}</div>{% endblock %}"""

T["users.html"] = """{% extends 'base.html' %}{% block body %}
<div class="card"><h4>Tài khoản</h4><div class="table-wrap"><table><tr><th>Tên đăng nhập</th><th>Vai trò</th><th>Thao tác</th></tr>
{% for u in users %}<tr><td>{{u.username}}</td><td><form method="post" action="{{url_for('change_role',name=u.username)}}">
<select name="role">{% for r in roles %}<option value="{{r}}" {{'selected' if u.role==r else ''}}>{{r}}</option>{% endfor %}</select><button type="submit">Lưu</button></form></td>
<td><form method="post" action="{{url_for('delete_user',name=u.username)}}" onsubmit="return confirm('Xóa tài khoản?')"><button type="submit">Xóa</button></form></td></tr>{% endfor %}</table></div></div>
<div class="card"><h4>Thêm tài khoản</h4><form method="post" action="{{url_for('create_user')}}">
<input name="username" placeholder="Tên đăng nhập" required minlength="3" maxlength="30">
<input name="password" type="password" placeholder="Mật khẩu (tối thiểu 6 ký tự)" required minlength="6">
<select name="role">{% for r in roles %}<option value="{{r}}">{{r}}</option>{% endfor %}</select><button type="submit">Tạo tài khoản</button></form></div>{% endblock %}"""

app.jinja_loader = DictLoader(T)


if __name__ == "__main__":
    try:
        # Kiểm tra kết nối và chuẩn bị collection tài khoản; không xóa dữ liệu.
        db.command("ping")
        seed_users()
        print("Database:", db.name)
        print("Collection sản phẩm:", product_collection.name)
        print("Số sản phẩm:", product_collection.count_documents({}))
    except Exception as exc:
        raise SystemExit(
            "Không kết nối được MongoDB Atlas. Kiểm tra MONGODB_URI trong .env "
            "và kết nối mạng.\n" + str(exc)
        )
    app.run(debug=True, port=5001)
