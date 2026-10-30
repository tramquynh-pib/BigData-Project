const c = db.getSiblingDB("Technology_market_analysis").product_listings;

// Mã 2.1.7.5 — kiểm tra BSON, 5 document như trong báo cáo.
print("Mã 2.1.7.5 - BSON types / embedded objects:");
printjson(c.aggregate([
  { $limit: 5 },
  { $project: {
    listing_id: 1,
    id_type: { $type: "$_id" },
    retailer_type: { $type: "$retailer" },
    brand_type: { $type: "$brand" },
    category_type: { $type: "$category" },
    sale_type: { $type: "$sale_price_vnd" },
    list_type: { $type: "$list_price_vnd" },
    date_type: { $type: "$crawled_at" }
  } }
]).toArray());

// Kiểm tra nhóm trùng trước khi tạo UNIQUE index.
const duplicateIdsBeforeIndex = c.aggregate([
  { $group: { _id: "$listing_id", n: { $sum: 1 } } },
  { $match: { n: { $gt: 1 } } }
]).toArray();
const duplicateUrlsBeforeIndex = c.aggregate([
  { $group: { _id: { source: "$retailer.source", url: "$product_url" }, n: { $sum: 1 } } },
  { $match: { n: { $gt: 1 } } }
]).toArray();
if (duplicateIdsBeforeIndex.length || duplicateUrlsBeforeIndex.length) {
  printjson({duplicateIdsBeforeIndex, duplicateUrlsBeforeIndex});
  throw new Error("Dữ liệu trùng: chưa thể tạo UNIQUE index");
}

// Mã 2.1.7.6 — sáu chỉ mục trong báo cáo.
c.createIndex({ listing_id: 1 }, { unique: true, name: "uq_listing_id" });
c.createIndex({ "retailer.source": 1, product_url: 1 }, { unique: true, name: "uq_retailer_url" });
c.createIndex({ "retailer.source": 1 }, { name: "idx_retailer" });
c.createIndex({ "brand.brand": 1 }, { name: "idx_brand" });
c.createIndex({ "category.category_context": 1 }, { name: "idx_category" });
c.createIndex({ sale_price_vnd: 1 }, { name: "idx_sale_price" });
print("Mã 2.1.7.6 - Indexes:");
printjson(c.getIndexes());

// ------------------------------------------------------------

// Mục 2.1.7.5 — truy vấn và kiểm chứng dữ liệu lưu trữ.
// Bộ lọc/projection Mã 2.1.7.8–2.1.7.9 có thể dán riêng vào Compass Documents.

// Mã 2.1.7.7 — đếm và thống kê theo website.
print("Mã 2.1.7.7 - Tổng document:");
printjson({ total_documents: c.countDocuments({}) });
print("Mã 2.1.7.7 - Phân bố retailer.source:");
printjson(c.aggregate([
  { $group: { _id: "$retailer.source", count: { $sum: 1 } } },
  { $sort: { count: -1 } }
]).toArray());

// Mã 2.1.7.8 — Compass Filter:
// {"retailer.source":"cellphones","sale_price_vnd":{"$gte":1000000}}
// Mã 2.1.7.9 — Compass Project:
// {"_id":0,"name":1,"retailer.source":1,"brand.brand":1,"sale_price_vnd":1}
print("Mã 2.1.7.8–2.1.7.9 - Năm niêm yết mẫu:");
printjson(c.find(
  { "retailer.source": "cellphones", sale_price_vnd: { $gte: 1000000 } },
  { _id: 0, name: 1, "retailer.source": 1, "brand.brand": 1, sale_price_vnd: 1 }
).limit(5).toArray());

// Mã 2.1.7.10 — kiểm tra trùng và giá không hợp lệ (kết quả tổng hợp như báo cáo).
const duplicateIds = c.aggregate([
  { $group: { _id: "$listing_id", n: { $sum: 1 } } },
  { $match: { n: { $gt: 1 } } }
]).toArray();
const duplicateUrls = c.aggregate([
  { $group: { _id: { source: "$retailer.source", url: "$product_url" }, n: { $sum: 1 } } },
  { $match: { n: { $gt: 1 } } }
]).toArray();
const invalidPrices = c.countDocuments({
  $or: [
    { sale_price_vnd: { $exists: false } },
    { sale_price_vnd: null },
    { sale_price_vnd: { $not: { $type: "number" } } },
    { sale_price_vnd: { $lte: 0 } }
  ]
});
print("Mã 2.1.7.10 - Kết quả kiểm tra:");
printjson({
  duplicate_listing_id_groups: duplicateIds.length,
  duplicate_retailer_url_groups: duplicateUrls.length,
  invalid_price_documents: invalidPrices
});
