"""Thu thập niêm yết sản phẩm công nghệ từ các website bán lẻ Việt Nam.

Chương trình đọc sitemap, chọn danh mục, kiểm tra robots.txt và trích xuất
sản phẩm từ HTML hoặc JSON-LD. Phản hồi gốc được lưu cùng thời điểm tải,
mã SHA-256 và thông tin nguồn để phục vụ đối chiếu, làm minh chứng.
"""
from __future__ import annotations
import argparse
import concurrent.futures
import csv
import gzip
import hashlib
import json
import os
import re
import sys
import time
import sqlite3
import urllib.request
import urllib.error
from datetime import datetime, timezone, timedelta
from pathlib import Path
from urllib.parse import urljoin, urlsplit, urlunsplit
try:
    from lxml import html, etree
except ImportError as error:
    raise SystemExit('Thiếu thư viện lxml. Cài bằng lệnh: python -m pip install lxml') from error

# Thư mục dự án, dữ liệu của đợt khảo sát và phản hồi gốc của từng nguồn.
BASE = Path(__file__).resolve().parent
DATA = BASE / 'data' / ('market_' + datetime.now(timezone(timedelta(hours=7))).strftime('%Y_%m_%d'))
RAW = DATA / 'raw'
DEFAULT_TARGET = 5150
DEFAULT_MAX_PAGES = 60
UA = 'AcademicMarketResearchCrawler/1.0'
# Cấu hình website, khoảng cách tối thiểu giữa các yêu cầu và URL sitemap.
SOURCES = {
 'cellphones': {'base':'https://cellphones.com.vn','delay':2,
               'sitemap':'https://cellphones.com.vn/sitemap/sitemap_index.xml?v=google'},
 'fptshop': {'base':'https://fptshop.com.vn','delay':2,
             'sitemap':'https://fptshop.com.vn/sitemap.xml'},
 'tgdd': {'base':'https://www.thegioididong.com','delay':5,
          'sitemap':'https://www.thegioididong.com/newsitemap/sitemap-cate'},
}
def now():
    """Trả về thời gian hiện tại theo ISO 8601 với múi giờ Việt Nam UTC+07:00."""
    return datetime.now(timezone(timedelta(hours=7))).isoformat()

def configure_output(output_dir=None):
    """Tạo thư mục đợt thu thập; hai file cùng ngày mặc định dùng chung nơi lưu.

    Có thể truyền --output-dir để chọn một thư mục mới hoặc tiếp tục đợt cũ.
    Không xóa dữ liệu có sẵn khi chạy lại.
    """
    global DATA, RAW
    if output_dir:
        DATA = Path(output_dir).expanduser().resolve()
    DATA.mkdir(parents=True, exist_ok=True)
    RAW = DATA / 'raw'
    RAW.mkdir(parents=True, exist_ok=True)
    return DATA

def record_error(stage, source, error):
    """Ghi lỗi vào JSONL để việc mạng lỗi hoặc nguồn đổi cấu trúc có minh chứng."""
    DATA.mkdir(parents=True, exist_ok=True)
    entry = {'time': now(), 'stage': stage, 'source': source, 'error': str(error)}
    with (DATA / 'errors.jsonl').open('a', encoding='utf-8') as stream:
        stream.write(json.dumps(entry, ensure_ascii=False) + '\n')
    print(json.dumps(entry, ensure_ascii=False), flush=True)

def listing_count():
    """Đếm niêm yết đã lưu để kiểm tra ngưỡng dừng trước khi kết nối mạng."""
    db = connect()
    try:
        return db.execute('SELECT COUNT(*) FROM listings').fetchone()[0]
    finally:
        db.close()
def norm(url):
    """Chuẩn hóa URL: bỏ khoảng trắng, fragment và dấu / cuối đường dẫn.

    Giữ nguyên tham số truy vấn để không làm thay đổi nội dung URL cần tải.
    """
    u=urlsplit(url.strip())
    return urlunsplit((u.scheme,u.netloc,u.path.rstrip('/') or '/',u.query,''))
def money(value):
    """Chuyển số hoặc chuỗi giá thành số nguyên VND; trả None nếu không hợp lệ.

    Ví dụ: '29.490.000đ' thành 29490000. Chuỗi có nội dung khác định dạng
    giá, chẳng hạn 'Liên hệ', không được tự chuyển thành một mức giá.
    """
    if value is None: return None
    value=str(value).strip()
    if re.fullmatch(r'\d+(?:\.\d{1,2})?',value): return int(float(value))
    if not re.fullmatch(r'[\d.,\s]+[đ₫]?',value): return None
    digits=re.sub(r'\D','',value)
    return int(digits) if digits else None
def clean(node):
    """Lấy văn bản trong phần tử HTML và gộp các khoảng trắng thừa."""
    return ' '.join(node.text_content().split())

# Danh mục gốc thuộc phạm vi sản phẩm công nghệ được chọn cho từng website.
TECH_ROOTS={
 'cellphones': {'mobile','laptop','tablet','phu-kien','thiet-bi-am-thanh','do-choi-cong-nghe',
               'may-tinh-de-ban','man-hinh','may-in','linh-kien','may-anh','flycam',
               'bang-ve-dien-tu','may-quay-phim','tivi'},
 'fptshop': {'dien-thoai','may-tinh-xach-tay','may-tinh-bang','phu-kien','smartwatch',
             'may-tinh-de-ban','man-hinh','may-in','linh-kien','camera','thiet-bi-choi-game',
             'may-chieu','may-choi-game','may-doc-sach','thiet-bi-mang','tivi'},
 'tgdd': {'dtdd','laptop','may-tinh-bang','phu-kien','sac-dtdd','sac-cap','adapter-sac',
          'cap-dien-thoai','op-lung-flipcover','mieng-dan-man-hinh','op-lung-may-tinh-bang',
          'do-choi-dien-thoai','phu-kien-laptop-PC','hub-chuyen-doi','chuot-may-tinh',
          'ban-phim','thiet-bi-mang','tui-chong-soc','tui-dung-phu-kien','mieng-phu-ban-phim',
          'gia-treo-man-hinh','mieng-lot-chuot','bang-ve-dien-tu','tai-nghe','loa-laptop',
          'micro-cac-loai','may-chieu','mat-kinh','o-cung-di-dong','the-nho','usb',
          'camera','camera-giam-sat','camera-hanh-trinh-hanh-dong','chuong-cua-camera',
          'may-anh','flycam','gay-tu-suong','dong-ho-thong-minh','dong-ho-thong-minh-ldp',
          'may-tinh-de-ban','man-hinh-may-tinh','may-choi-game-cam-tay','bo-luu-dien',
          'thiet-bi-ma-vach','muc-in','may-in','dau-ghi-camera','ong-kinh-tele',
          'may-anh-va-phu-kien','phu-kien-may-anh','loa-tai-nghe','chuot-ban-phim',
          'mieng-dan-op-lung','gia-do-dien-thoai','tui-dung-airpods','day-dong-ho','airtag',
          'phu-kien-gaming','phu-kien-dien-thoai','phu-kien-may-tinh','pin','thiet-bi-luu-tru'},
}
# Ánh xạ mã đường dẫn danh mục sang tên nhóm tiếng Việt.
GROUPS={'mobile':'Điện thoại','dtdd':'Điện thoại','dien-thoai':'Điện thoại',
        'laptop':'Laptop','may-tinh-xach-tay':'Laptop','tablet':'Máy tính bảng',
        'may-tinh-bang':'Máy tính bảng','phu-kien':'Phụ kiện công nghệ',
        'thiet-bi-am-thanh':'Thiết bị âm thanh','do-choi-cong-nghe':'Thiết bị đeo',
        'smartwatch':'Thiết bị đeo','dong-ho-thong-minh':'Thiết bị đeo',
        'dong-ho-thong-minh-ldp':'Thiết bị đeo','linh-kien':'Linh kiện máy tính',
        'man-hinh':'Màn hình','man-hinh-may-tinh':'Màn hình','may-tinh-de-ban':'Máy tính để bàn',
        'may-in':'Máy in','camera':'Camera và máy ảnh','may-anh':'Camera và máy ảnh',
        'flycam':'Flycam','tivi':'Tivi'}
# Danh sách dùng để nhận diện thương hiệu trong tên khi nguồn thiếu trường này.
BRANDS=['Samsung','Apple','Xiaomi','OPPO','Vivo','Realme','Honor','Nokia','Tecno','Nubia',
        'Meizu','Itel','Infinix','Nothing','Benco','Masstel','Mobell','Sony','Asus','Acer',
        'Lenovo','Dell','HP','MSI','LG','Huawei','Microsoft','Gigabyte','Intel','AMD','Kingston',
        'Corsair','Logitech','Razer','DareU','E-Dra','TP-Link','D-Link','Tenda','Anker','Baseus',
        'Ugreen','Belkin','Mophie','Satechi','JBL','Bose','Sennheiser','Marshall','Edifier',
        'Soundpeats','Havit','Energizer','SanDisk','Seagate','Western Digital','Lexar','Adata',
        'Crucial','Canon','Epson','Brother','Fujifilm','Nikon','Panasonic','DJI','GoPro',
        'Insta360','Imou','Ezviz','Hikvision','Dahua','Xtel','Xmobile','Amazfit','Garmin',
        'Coros','Suunto','Haylou','TCL','Viewsonic','Philips','BenQ','AOC','Wacom','XP-Pen']
# Lọc thêm một số sản phẩm ngoài phạm vi có thể xuất hiện trong danh mục.
NON_TECH=re.compile(r'\b(nồi|chảo|bếp|tủ lạnh|máy giặt|máy sấy tóc|máy lọc nước|máy hút bụi|bình giữ nhiệt|kem đánh răng|bàn chải|máy cạo râu|máy massage)\b',re.I)

def root_slug(url):
    """Lấy đoạn đầu của đường dẫn danh mục và bỏ đuôi .html nếu có."""
    return urlsplit(url).path.strip('/').split('/')[0].removesuffix('.html')
def chosen_categories(source):
    """Đọc danh mục đã phát hiện và chọn các URL thuộc phạm vi công nghệ.

    Bỏ URL có tham số truy vấn, sắp xếp trang ít cấp đường dẫn trước để
    khảo sát danh mục tổng quát trước các danh mục con.
    """
    urls=json.loads((DATA/(source+'_categories_all.json')).read_text(encoding='utf-8'))
    urls=[u for u in urls if root_slug(u) in TECH_ROOTS[source] and not urlsplit(u).query]
    return sorted(urls,key=lambda u:(urlsplit(u).path.count('/'),u))

def guess_brand(name):
    """Suy đoán thương hiệu từ tên sản phẩm bằng các quy tắc nhận diện.

    Trả chuỗi rỗng nếu không nhận diện được. Kết quả cần được kiểm tra lại
    khi phân tích vì tên có thể nhắc đến thương hiệu thiết bị tương thích.
    """
    if re.match(r'^(?:Điện thoại\s+)?(?:iPhone|iPad|MacBook|iMac|AirPods|Apple Watch)\b',name,re.I):return 'Apple'
    for brand in BRANDS:
        if re.search(r'(?<!\w)'+re.escape(brand)+r'(?!\w)',name,re.I):return brand
    return ''

def extract_listings(source,response):
    """Trích xuất và chuẩn hóa các niêm yết trong một phản hồi danh mục.

    Thế Giới Di Động được đọc từ JSON-LD; CellphoneS và FPT Shop được đọc
    từ thẻ sản phẩm trong HTML. Chỉ giữ tên, giá và URL đạt điều kiện lọc;
    loại trùng URL trong phản hồi và gắn thông tin minh chứng cho mỗi dòng.
    """
    tree=html.fromstring(response['text'])
    rows=[]
    if source=='tgdd':
        # Tìm danh sách Product nằm trong dữ liệu cấu trúc CollectionPage.
        for script in tree.xpath('//script[@type="application/ld+json"]'):
            try:data=json.loads(script.text or '{}')
            except ValueError:continue
            if not isinstance(data,dict) or data.get('@type')!='CollectionPage':continue
            for entry in data.get('mainEntity',{}).get('itemListElement',[]):
                product=entry.get('item',{});offer=product.get('offers',{})
                if isinstance(offer,list):offer=offer[0] if offer else {}
                if product.get('name') and product.get('url'):
                    rows.append({'name':product['name'],'product_url':product['url'],
                                 'sale_price_vnd':money(offer.get('price')),'list_price_vnd':None,
                                 'availability':offer.get('availability',''),
                                 'extraction_method':'JSON-LD ItemList Product',
                                 'brand':product.get('brand',{}).get('name','')})
    else:
        # Dùng thẻ tên sản phẩm và lớp CSS của giá tương ứng với từng nguồn.
        for heading in tree.xpath('//h3'):
            links=heading.xpath('ancestor::a[1]')
            if not links:continue
            link=links[0]
            if source=='cellphones':
                prices=link.xpath('.//*[contains(@class,"product__price--show")]')
                original=link.xpath('.//*[contains(@class,"product__price--through")]')
            else:
                prices=link.xpath('.//p[contains(@class,"b1-semibold")]')
                original=link.xpath('.//*[contains(@class,"line-through")]')
            if not prices:continue
            rows.append({'name':clean(heading),'product_url':urljoin(SOURCES[source]['base'],link.get('href','')),
                         'sale_price_vnd':money(clean(prices[0])),
                         'list_price_vnd':money(clean(original[0])) if original else None,
                         'availability':'','extraction_method':'HTML product card','brand':''})
    unique={}
    for row in rows:
        # Kiểm tra giá, tên và tên miền trước khi đưa vào tập kết quả.
        price=row['sale_price_vnd'];url=norm(row['product_url'])
        if not price or not 1000<=price<=2_000_000_000:continue
        if len(row['name'])<4 or NON_TECH.search(row['name']):continue
        if urlsplit(url).netloc!=urlsplit(SOURCES[source]['base']).netloc:continue
        if url==norm(response['url']):continue
        # Danh mục chỉ là ngữ cảnh trang; khu vực giá HTML chưa được xác minh.
        row.update(product_url=url,source=source,brand=row['brand'] or guess_brand(row['name']),
                   category_context=GROUPS.get(root_slug(response['url']),'Phụ kiện và thiết bị công nghệ'),
                   category_context_slug=root_slug(response['url']),
                   category_context_verified=False,
                   currency='VND',price_region='website_default_unverified',
                   crawled_at=response['fetched_at'],source_page_url=response['url'],
                   evidence_sha256=response['sha256'],evidence_file=response['raw_file'])
        row['listing_id']=hashlib.sha256((source+'|'+url).encode()).hexdigest()[:24]
        unique.setdefault(url,row)
    return list(unique.values())

def connect():
    """Mở SQLite và tạo bảng lưu niêm yết cùng nhật ký trang thu thập.

    Khóa chính (source, url) giúp loại trùng theo website và URL sản phẩm.
    Chế độ WAL hỗ trợ các luồng dùng kết nối riêng cùng truy cập dữ liệu.
    """
    DATA.mkdir(parents=True,exist_ok=True)
    db=sqlite3.connect(DATA/'market.sqlite',timeout=30)
    db.execute('PRAGMA journal_mode=WAL')
    db.execute('CREATE TABLE IF NOT EXISTS listings (source TEXT, url TEXT, payload TEXT, PRIMARY KEY(source,url))')
    db.execute('CREATE TABLE IF NOT EXISTS pages (source TEXT, url TEXT, status TEXT, rows INTEGER, error TEXT, PRIMARY KEY(source,url))')
    return db
def export_data(db, target=DEFAULT_TARGET):
    """Xuất niêm yết trong SQLite thành CSV UTF-8, JSONL và thống kê JSON.

    Trả về thống kê số bản ghi theo nguồn và số trang đã xử lý hoặc gặp lỗi.
    Tự tạo tài liệu hướng dẫn và kết quả kiểm tra trong cùng thư mục; không
    phụ thuộc file finalize_market_dataset.py hoặc bộ dữ liệu tải sẵn.
    """
    rows=[json.loads(r[0]) for r in db.execute('SELECT payload FROM listings ORDER BY source,url')]
    fields=list(rows[0]) if rows else ['listing_id','name','product_url','sale_price_vnd','source','crawled_at']
    with (DATA/'market_listings.csv').open('w',encoding='utf-8-sig',newline='') as f:
        writer=csv.DictWriter(f,fieldnames=fields);writer.writeheader();writer.writerows(rows)
    with (DATA/'market_listings.jsonl').open('w',encoding='utf-8') as f:
        for row in rows:f.write(json.dumps(row,ensure_ascii=False)+'\n')
    counts={s:n for s,n in db.execute('SELECT source,COUNT(*) FROM listings GROUP BY source')}
    stats={'exported_at':now(),'unique_listings':len(rows),'by_source':counts,
           'category_pages_processed':db.execute('SELECT COUNT(*) FROM pages').fetchone()[0],
           'page_errors':db.execute("SELECT COUNT(*) FROM pages WHERE status='error'").fetchone()[0],
           'target':target,'target_reached':len(rows)>=target,
           'unit':'Một URL niêm yết khác nhau tại mỗi website; không phải số model khác nhau',
           'unverified_price_region':sum(r.get('price_region')=='website_default_unverified' for r in rows),
           'unverified_category_context':sum(not r.get('category_context_verified') for r in rows),
           'duplicate_keys':len(rows)-len({(r['source'],r['product_url']) for r in rows}),
           'invalid_name_or_price':sum(not r.get('name') or not r.get('sale_price_vnd') or r['sale_price_vnd']<=0 for r in rows),
           'first_crawled_at':min((r['crawled_at'] for r in rows),default=None),
           'last_crawled_at':max((r['crawled_at'] for r in rows),default=None),
           'data_directory':str(DATA)}
    (DATA/'summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
    instructions = f'''# Dữ liệu sản phẩm công nghệ tự thu thập

Số niêm yết: {len(rows)}. Mục tiêu: {target}. Đạt mục tiêu: {stats['target_reached']}.

- market_listings.csv: dữ liệu CSV UTF-8 có BOM, mở bằng Excel hoặc đọc bằng Python.
- market_listings.jsonl: cùng dữ liệu, mỗi dòng là một đối tượng JSON.
- market.sqlite: cơ sở dữ liệu loại trùng theo website + URL.
- summary.json: thống kê số dòng, lỗi và kết quả kiểm tra.
- raw/ và public_api/: phản hồi nguồn nén gzip cùng metadata URL, thời gian, SHA-256; truy vấn API nếu có.
- errors.jsonl: nhật ký lỗi nếu có. Dữ liệu chưa đạt mục tiêu vẫn được giữ lại để tiếp tục.

Chạy collect_market_data.py để tự tìm sitemap, danh mục và lấy dữ liệu HTML/JSON-LD
từ ba nhà bán lẻ. Mặc định khảo sát tối đa {DEFAULT_MAX_PAGES} danh mục mỗi nguồn.
Sau đó chạy collect_public_catalog.py để bổ sung danh mục CellphoneS đến ngưỡng
hoặc hết dữ liệu. Hai file phải được đặt cạnh nhau. Cần Python và thư viện lxml
(python -m pip install lxml). Không cần các file probe hoặc finalize.

Hai chương trình mặc định lưu cùng thư mục theo ngày chạy tại Việt Nam. Chạy lại
cùng thư mục sẽ tiếp tục dữ liệu đã có và dùng cache. Muốn thu thập một đợt mới,
dùng cùng một --output-dir mới cho cả hai chương trình; không cần xóa dữ liệu cũ.

Mỗi dòng có URL sản phẩm, thời điểm thu thập, evidence_file và evidence_sha256.
Đường dẫn evidence_file được tính từ thư mục chứa hai mã nguồn. Giá là giá hiển thị
trên website, không phải giao dịch. Thương hiệu suy ra từ tên cần kiểm tra lại.
category_context_verified=False nghĩa là nhóm chỉ theo ngữ cảnh trang tìm thấy.
price_region=website_default_unverified nghĩa là khu vực giá chưa xác minh.
Các bản ghi API province_id=30 thuộc Hồ Chí Minh. Cùng model ở nhiều website
được giữ thành nhiều niêm yết. Dữ liệu này không cung cấp lịch sử mua của khách hàng.
'''
    (DATA/'README.md').write_text(instructions,encoding='utf-8')
    return stats

def harvest(source,target,max_pages):
    """Thu thập lần lượt các trang danh mục của một website.

    target là ngưỡng tổng bản ghi trong cơ sở dữ liệu để dừng giữa các lượt;
    max_pages giới hạn số trang xét đến, bằng 0 thì không giới hạn. Bỏ qua
    trang đã ghi nhật ký, lưu các dòng mới và ghi nhận lỗi của từng trang.
    """
    if listing_count()>=target:
        return
    client=Client(source)
    # Tự chuẩn bị từ số 0: không yêu cầu người dùng chạy các bước phụ trước.
    if not (DATA/(source+'_categories_all.json')).exists():
        discover_categories(source,client=client)
    db=connect();pages=chosen_categories(source)
    if max_pages:pages=pages[:max_pages]
    for index,url in enumerate(pages,1):
        if db.execute('SELECT COUNT(*) FROM listings').fetchone()[0]>=target:break
        if db.execute("SELECT 1 FROM pages WHERE source=? AND url=? AND status='ok'",(source,url)).fetchone():continue
        if not client.permitted(url):continue
        try:
            response=client.fetch(url);rows=extract_listings(source,response)
            with db:
                for row in rows:
                    # Giữ lần ghi nhận đầu tiên nếu cùng URL đã có tại nguồn.
                    db.execute('INSERT OR IGNORE INTO listings VALUES (?,?,?)',
                               (source,row['product_url'],json.dumps(row,ensure_ascii=False)))
                db.execute('INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?)',(source,url,'ok',len(rows),''))
        except Exception as error:
            with db:db.execute('INSERT OR REPLACE INTO pages VALUES (?,?,?,?,?)',
                               (source,url,'error',0,str(error)))
            print(json.dumps({'source':source,'page':index,'error':str(error)},ensure_ascii=False),flush=True)
            if isinstance(error,urllib.error.HTTPError) and error.code in (403,429):
                # Dừng nguồn khi bị từ chối truy cập hoặc yêu cầu giảm tải.
                print(source+' paused after HTTP '+str(error.code),flush=True);break
        if index%10==0:
            count=db.execute('SELECT COUNT(*) FROM listings').fetchone()[0]
            print(json.dumps({'source':source,'page':index,'of':len(pages),'total_unique':count},ensure_ascii=False),flush=True)
    db.close()

class Client:
    """Quản lý tải trang, quy tắc robots.txt và bộ nhớ đệm cho một website."""

    def __init__(self,source,config=None,allow_missing_robots=False):
        """Tạo nơi lưu và tự kiểm tra robots; API có thể trả 404 cho tệp này.

        config cho phép dùng cùng bộ kiểm tra cho tên miền API. Chỉ coi
        robots là không tồn tại khi nhận đúng HTTP 404, không bỏ qua lỗi 403.
        """
        self.source=source; self.cfg=config or SOURCES[source]; self.last=0
        self.root=RAW/source; self.root.mkdir(parents=True,exist_ok=True)
        self.rules=[]; self.delay=self.cfg['delay']
        try:
            self.robots=self.fetch(self.cfg['base']+'/robots.txt',force_policy=True)
        except urllib.error.HTTPError as error:
            if not allow_missing_robots or error.code!=404:
                raise
            self.robots={'url':self.cfg['base']+'/robots.txt','http_status':404,
                         'fetched_at':now(),'text':''}
        check={k:v for k,v in self.robots.items() if k!='text'}
        (self.root/'robots_check.json').write_text(json.dumps(check,ensure_ascii=False,indent=2),encoding='utf-8')
        self._parse_robots(self.robots['text'])
    def _parse_robots(self,text):
        """Phân tích Allow, Disallow và Crawl-delay trong nội dung robots.txt.

        Chọn nhóm User-agent phù hợp, hỗ trợ ký tự đại diện * và ký hiệu $
        ở cuối mẫu đường dẫn; giữ quy tắc để kiểm tra trước khi tải trang.
        """
        agents=[]; entries=[]; groups=[]
        for line in text.splitlines()+['User-agent: __end__']:
            line=line.split('#',1)[0].strip()
            if ':' not in line: continue
            key,value=map(str.strip,line.split(':',1)); key=key.lower()
            if key=='user-agent':
                if entries: groups.append((agents,entries)); agents=[]; entries=[]
                agents.append(value.lower())
            else: entries.append((key,value))
        selected=[g for g in groups if any(a!='*' and a in UA.lower() for a in g[0])]
        if not selected: selected=[g for g in groups if '*' in g[0]]
        for _,entries in selected:
            for key,value in entries:
                if key=='crawl-delay':
                    try:self.delay=max(self.delay,float(value))
                    except ValueError:pass
                if key in ('allow','disallow') and value:
                    anchored=value.endswith('$'); value=value.rstrip('$') if anchored else value
                    pattern='^'+re.escape(value).replace(r'\*','.*')+('$' if anchored else '')
                    self.rules.append((re.compile(pattern),key=='allow',len(value.replace('*',''))))
    def permitted(self,url):
        """Kiểm tra URL cùng tên miền và được phép theo các quy tắc đã nạp.

        Ưu tiên mẫu khớp cụ thể nhất; nếu độ dài bằng nhau, Allow được ưu tiên.
        """
        u=urlsplit(url)
        if u.netloc!=urlsplit(self.cfg['base']).netloc:return False
        path=u.path+('?' + u.query if u.query else '')
        matches=[(length,allow) for pattern,allow,length in self.rules if pattern.search(path)]
        return not matches or max(matches)[1]
    def fetch(self,url,force_policy=False):
        """Đọc phản hồi đã lưu hoặc gửi HTTP GET rồi lưu dữ liệu minh chứng.

        Kết quả gồm nội dung văn bản, URL, thời điểm, trạng thái và SHA-256.
        Phản hồi được nén gzip, metadata được lưu riêng dưới dạng JSON.
        force_policy bỏ bước xét robots cho tệp quy tắc hoặc sitemap được
        chỉ định; khi dùng cache, giữ nguyên thời điểm tải ban đầu.
        """
        return self.request(url,force_policy=force_policy)

    def request(self,url,payload=None,headers=None,force_policy=False):
        """Tải GET hoặc POST chỉ đọc, kiểm tra quyền truy cập và lưu cache.

        POST được dùng cho truy vấn danh mục, khóa cache gồm cả URL và
        nội dung yêu cầu. Chỉ thử lại lỗi mạng hoặc HTTP 5xx tối đa hai lần;
        lỗi 403/429 được trả ngay để nguồn dừng thu thập.
        """
        url=norm(url)
        if not force_policy and not self.permitted(url):
            raise PermissionError('robots.txt excludes '+url)
        cache_key=url.encode()+(b'\n'+payload if payload is not None else b'')
        key=hashlib.sha256(cache_key).hexdigest()
        meta_path=self.root/(key+'.json'); raw_path=self.root/(key+'.gz')
        if meta_path.exists() and raw_path.exists():
            # Tái sử dụng phản hồi cũ để tránh gửi yêu cầu trùng lặp.
            meta=json.loads(meta_path.read_text(encoding='utf-8'))
            meta['text']=gzip.decompress(raw_path.read_bytes()).decode('utf-8',errors='replace')
            return meta
        request_headers={'User-Agent':UA,'Accept-Encoding':'identity',**(headers or {})}
        for attempt in range(3):
            # Khoảng cách giữa các lần bắt đầu gửi yêu cầu, kể cả khi thử lại.
            time.sleep(max(0,self.last+self.delay-time.monotonic()))
            self.last=time.monotonic()
            req=urllib.request.Request(url,data=payload,headers=request_headers)
            try:
                with urllib.request.urlopen(req,timeout=30) as response:
                    raw=response.read(25_000_000)
                    if len(raw)>=25_000_000:raise ValueError('Response exceeds size limit')
                    meta={'url':url,'final_url':response.url,'http_status':response.status,
                          'fetched_at':now(),'content_type':response.headers.get('Content-Type'),
                          'bytes':len(raw),'sha256':hashlib.sha256(raw).hexdigest(),
                          'raw_file':os.path.relpath(raw_path,BASE),
                          'method':'POST read-only GraphQL query' if payload is not None else 'GET'}
                    if payload is not None:
                        meta['request_body']=json.loads(payload)
                break
            except urllib.error.HTTPError as error:
                if error.code<500 or attempt==2:raise
            except (urllib.error.URLError,TimeoutError,OSError):
                if attempt==2:raise
            time.sleep(2*(attempt+1))
        raw_path.write_bytes(gzip.compress(raw))
        meta_path.write_text(json.dumps(meta,ensure_ascii=False,indent=2),encoding='utf-8')
        meta['text']=raw.decode('utf-8',errors='replace')
        return meta

def sitemap_locs(response):
    """Đọc XML sitemap, trả loại sitemap và danh sách URL trong các thẻ loc."""
    root=etree.fromstring(response['text'].encode(),parser=etree.XMLParser(recover=True))
    return root.tag.split('}')[-1],root.xpath('//*[local-name()="loc"]/text()')

def discover(source,client=None):
    """Tải sitemap đầu vào của nguồn và lưu các URL phát hiện được vào JSON."""
    client=client or Client(source)
    result=client.fetch(client.cfg['sitemap'],force_policy=True)
    kind,locs=sitemap_locs(result)
    report={'source':source,'kind':kind,'count':len(locs),'locs':locs}
    (DATA/(source+'_sitemap.json')).write_text(json.dumps(report,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'source':source,'kind':kind,'count':len(locs),'sample':locs[:30]},ensure_ascii=False),flush=True)
    return report

def discover_categories(source,client=None):
    """Tạo danh sách URL danh mục từ kết quả khảo sát sitemap đầu vào.

    Với sitemap dạng chỉ mục, tải tiếp các sitemap danh mục của CellphoneS
    hoặc FPT Shop. Với nguồn đã liệt kê trực tiếp URL danh mục, dùng ngay
    danh sách đó, loại trùng và lưu vào tệp *_categories_all.json.
    """
    client=client or Client(source)
    if not (DATA/(source+'_sitemap.json')).exists():
        discover(source,client=client)
    sitemap=json.loads((DATA/(source+'_sitemap.json')).read_text(encoding='utf-8'))
    urls=[]
    if source=='cellphones':maps=[u for u in sitemap['locs'] if '/category-sitemap' in u]
    elif source=='fptshop':maps=[u for u in sitemap['locs'] if 'sitemap-category.xml' in u]
    else:maps=[];urls=sitemap['locs']
    for url in maps:
        response=client.fetch(url)
        _,locs=sitemap_locs(response);urls.extend(locs)
    urls=sorted(set(map(norm,urls)))
    (DATA/(source+'_categories_all.json')).write_text(json.dumps(urls,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'source':source,'categories':len(urls),'sample':urls[:65]},ensure_ascii=False),flush=True)

def run_sources(stage,action,sources):
    """Chạy độc lập từng nguồn và ghi rõ nguồn thất bại, không che lỗi khởi tạo."""
    failures=[]
    with concurrent.futures.ThreadPoolExecutor(max_workers=len(sources)) as pool:
        futures={pool.submit(action,source):source for source in sources}
        for future in concurrent.futures.as_completed(futures):
            try:
                future.result()
            except Exception as error:
                failures.append(futures[future])
                record_error(stage,futures[future],error)
    return failures

def main(argv=None):
    """Chạy trực tiếp là tự chuẩn bị và crawl; các tùy chọn dùng khi cần nâng cao.

    Không truyền tùy chọn thao tác thì tự chạy --crawl. Danh mục và sitemap
    thiếu được tạo tự động trong harvest; nhiều tùy chọn được thực hiện theo
    thứ tự sitemap, danh mục, crawl, xuất để chạy được từ thư mục trống.
    """
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='Tự thu thập sản phẩm công nghệ từ ba website bán lẻ.')
    parser.add_argument('--discover',action='store_true',help='Khảo sát sitemap')
    parser.add_argument('--categories',action='store_true',help='Tự chuẩn bị danh sách danh mục')
    parser.add_argument('--crawl',action='store_true',help='Thu thập; mặc định khi bấm Run')
    parser.add_argument('--export',action='store_true',help='Chỉ xuất dữ liệu đã có')
    parser.add_argument('--target',type=int,default=DEFAULT_TARGET,help='Ngưỡng tổng niêm yết mong muốn')
    parser.add_argument('--max-pages',type=int,default=DEFAULT_MAX_PAGES,help='Số danh mục mỗi nguồn; 0 là tất cả')
    parser.add_argument('--output-dir',help='Thư mục dữ liệu; mặc định data/market_YYYY_MM_DD')
    parser.add_argument('--sources',nargs='+',choices=list(SOURCES),default=list(SOURCES))
    args=parser.parse_args(argv)
    if args.target<1 or args.max_pages<0:
        parser.error('--target phải dương và --max-pages không được âm')
    configure_output(args.output_dir)
    if not any((args.discover,args.categories,args.crawl,args.export)):
        args.crawl=True
    print('Thư mục dữ liệu: '+str(DATA),flush=True)
    failures=[]
    if args.discover:
        failures+=run_sources('sitemap',discover,args.sources)
    if args.categories:
        failures+=run_sources('danh_muc',discover_categories,args.sources)
    if args.crawl:
        print('Tự chuẩn bị nguồn và thu thập. Sau bước này chạy collect_public_catalog.py để bổ sung.',flush=True)
        db=connect();db.close()
        failures+=run_sources('crawl',lambda source:harvest(source,args.target,args.max_pages),args.sources)
    db=connect()
    try:
        stats=export_data(db,target=args.target)
    finally:
        db.close()
    print(json.dumps(stats,ensure_ascii=False,indent=2),flush=True)
    if not stats['target_reached']:
        print('Đã lưu '+str(stats['unique_listings'])+' niêm yết. Chạy tiếp: python collect_public_catalog.py'
              +(' --output-dir "'+str(DATA)+'"' if args.output_dir else ''),flush=True)
    if args.crawl and not stats['unique_listings']:
        print('Chưa thu được bản ghi nào; xem lỗi mạng hoặc errors.jsonl.',file=sys.stderr)
        return 1
    return 1 if failures else 0

if __name__=='__main__':
    raise SystemExit(main())
