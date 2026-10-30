/**
 * mongodb_main.js — Mục 1.7.4 và 1.7.5 trong báo cáo Big Data.
 * Chạy bằng mongosh sau khi đã import products_embedding.json vào
 * Technology_market_analysis.product_listings.
 */

const c = db.getSiblingDB('Technology_market_analysis').product_listings;

// ============================================================
// 1.7.4.a — Code 1. Kiểm tra cấu trúc BSON trên 5 document
// ============================================================
print('\n[1.7.4.a] Kiểm tra kiểu BSON / ba sub-document:');
printjson(c.aggregate([
  { $limit: 5 },
  {
    $project: {
      listing_id: 1,
      id_type: { $type: '$_id' },
      retailer_type: { $type: '$retailer' },
      brand_type: { $type: '$brand' },
      category_type: { $type: '$category' },
      sale_type: { $type: '$sale_price_vnd' },
      list_type: { $type: '$list_price_vnd' },
      date_type: { $type: '$crawled_at' }
    }
  }
]).toArray());

// ============================================================
// 1.7.4.b — Kiểm tra khóa trùng TRƯỚC KHI tạo UNIQUE index
// (Bước kiểm soát bổ sung có trong file JS nhóm đã cung cấp.)
// ============================================================
const duplicateIdsBeforeIndex = c.aggregate([
  { $group: { _id: '$listing_id', n: { $sum: 1 } } },
  { $match: { n: { $gt: 1 } } }
]).toArray();

const duplicateUrlsBeforeIndex = c.aggregate([
  {
    $group: {
      _id: { source: '$retailer.source', url: '$product_url' },
      n: { $sum: 1 }
    }
  },
  { $match: { n: { $gt: 1 } } }
]).toArray();

if (duplicateIdsBeforeIndex.length || duplicateUrlsBeforeIndex.length) {
  print('Phát hiện khóa trùng; dừng trước khi tạo UNIQUE index:');
  printjson({ duplicateIdsBeforeIndex, duplicateUrlsBeforeIndex });
  throw new Error('Dữ liệu trùng: chưa thể tạo UNIQUE index');
}

// ============================================================
// 1.7.4.b — Code 2. Thiết lập và kiểm tra chỉ mục
// Hai UNIQUE, bốn index thường; cùng _id_ mặc định là 7.
// ============================================================
c.createIndex({ listing_id: 1 }, { unique: true, name: 'uq_listing_id' });
c.createIndex(
  { 'retailer.source': 1, product_url: 1 },
  { unique: true, name: 'uq_retailer_url' }
);
c.createIndex({ 'retailer.source': 1 }, { name: 'idx_retailer' });
c.createIndex({ 'brand.brand': 1 }, { name: 'idx_brand' });
c.createIndex({ 'category.category_context': 1 }, { name: 'idx_category' });
c.createIndex({ sale_price_vnd: 1 }, { name: 'idx_sale_price' });
print('\n[1.7.4.b] Danh sách chỉ mục:');
printjson(c.getIndexes());

// ============================================================
// 1.7.5.a — Code 1. Đếm tổng và thống kê theo website
// ============================================================
print('\n[1.7.5.a] Tổng số document:');
printjson({ total_documents: c.countDocuments({}) });
print('[1.7.5.a] Phân bố theo retailer.source:');
printjson(c.aggregate([
  { $group: { _id: '$retailer.source', count: { $sum: 1 } } },
  { $sort: { count: -1 } }
]).toArray());

// ============================================================
// 1.7.5.b — Code 2. Filter và Code 3. Project
// Trong Compass Documents, dán RIÊNG hai đối tượng sau:
// Filter:  {"retailer.source":"cellphones","sale_price_vnd":{"$gte":1000000}}
// Project: {"_id":0,"name":1,"retailer.source":1,"brand.brand":1,"sale_price_vnd":1}
// Lệnh tương đương trong mongosh (giới hạn 5 mẫu để xem nhanh):
// ============================================================
print('\n[1.7.5.b] Năm niêm yết CellphoneS giá >= 1.000.000 VND:');
printjson(c.find(
  { 'retailer.source': 'cellphones', sale_price_vnd: { $gte: 1000000 } },
  { _id: 0, name: 1, 'retailer.source': 1, 'brand.brand': 1, sale_price_vnd: 1 }
).limit(5).toArray());

// ============================================================
// 1.7.5.c — Code 4. Kiểm tra ID trùng, nguồn–URL trùng và giá sai
// ============================================================
const duplicateIds = c.aggregate([
  { $group: { _id: '$listing_id', n: { $sum: 1 } } },
  { $match: { n: { $gt: 1 } } }
]).toArray();

const duplicateUrls = c.aggregate([
  {
    $group: {
      _id: { source: '$retailer.source', url: '$product_url' },
      n: { $sum: 1 }
    }
  },
  { $match: { n: { $gt: 1 } } }
]).toArray();

const invalidPrices = c.countDocuments({
  $or: [
    { sale_price_vnd: { $exists: false } },
    { sale_price_vnd: null },
    { sale_price_vnd: { $not: { $type: 'number' } } },
    { sale_price_vnd: { $lte: 0 } }
  ]
});

print('\n[1.7.5.c] Kết quả kiểm tra bất thường:');
printjson({
  duplicate_listing_id_groups: duplicateIds.length,
  duplicate_retailer_url_groups: duplicateUrls.length,
  invalid_price_documents: invalidPrices
});
