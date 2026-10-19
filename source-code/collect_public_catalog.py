"""Thu thập danh mục CellphoneS qua truy vấn chỉ đọc của giao diện công khai.

Endpoint, cấu trúc truy vấn, mã khu vực và mã tồn kho được xác định từ
JavaScript công khai của website. Các phản hồi được lưu làm minh chứng,
sau đó sản phẩm được chuẩn hóa và ghép vào cơ sở dữ liệu thu thập chung.
"""
import argparse,hashlib,json,sys,urllib.error
from urllib.parse import urljoin,urlsplit
import collect_market_data as c

# Địa chỉ truy vấn danh mục công khai và thư mục lưu phản hồi API.
ENDPOINT='https://api.cellphones.com.vn/v2/graphql/query'
RAW=c.DATA/'public_api'
# Ngưỡng tổng bản ghi để dừng; kiểm tra giữa các trang nên có thể vượt ngưỡng.
TARGET=5150
# Mã khu vực Hồ Chí Minh dùng để ghi lại phạm vi giá của phản hồi API.
PROVINCE=30
API_CLIENT=None
# Các danh mục bắt đầu: mã danh mục, đường dẫn và tên nhóm tiếng Việt.
ROOTS=[(30,'phu-kien','Phụ kiện công nghệ'),(220,'thiet-bi-am-thanh','Thiết bị âm thanh'),
       (610,'do-choi-cong-nghe','Thiết bị đeo')]

def query_page(category,page,size=50):
    """Tạo truy vấn GraphQL lấy một trang sản phẩm của danh mục được chọn.

    category là mã danh mục, page là số trang, size mặc định 50 sản phẩm.
    Truy vấn sử dụng khu vực Hồ Chí Minh (mã 30), lấy thông tin sản phẩm,
    danh mục và giá; các mã trạng thái hàng theo giao diện website là
    46 (InStock), 152 (PreOrder) và 4920 (VirtualStock).
    """
    return '''query GetProductsByCateId {
 products(filter:{static:{categories:["%s"],province_id:30,stock:{from:0},company_stock_id:[46,152,4920]},dynamic:{}},page:%d,size:%d,sort:[{view:desc}]) {
 general {product_id name sku manufacturer url_key url_path categories {categoryId name uri} review {total_count average_rating}}
 filterable {price special_price display_root_price display_price stock_available_id company_stock_id is_parent}
 }
}'''%(category,page,size)

def fetch(query):
    """Gửi truy vấn chỉ đọc bằng HTTP POST hoặc đọc lại phản hồi trong cache.

    Dùng SHA-256 của nội dung yêu cầu để nhận diện truy vấn đã tải. Lưu
    JSON phản hồi dưới dạng gzip cùng metadata chứa truy vấn, thời điểm
    và SHA-256 của phản hồi. Trả về cặp (metadata, dữ liệu JSON đã đọc).
    """
    client=ensure_api_client()
    payload=json.dumps({'query':query,'variables':{}}).encode()
    response=client.request(ENDPOINT,payload=payload,
                            headers={'Content-Type':'application/json','X-Client-Type':'web'})
    meta={k:v for k,v in response.items() if k!='text'}
    meta.update(query=query,province_id=PROVINCE)
    data=json.loads(response['text'])
    # HTTP thành công chưa đủ: phản hồi còn phải có danh sách products hợp lệ.
    if data.get('errors'):raise ValueError(str(data['errors']))
    if not isinstance(data.get('data',{}).get('products'),list):raise ValueError('Missing products array')
    return meta,data

def ensure_api_client():
    """Tự kiểm tra robots.txt của API, không cần chạy file probe bên ngoài.

    HTTP 404 nghĩa là tên miền không trả tệp robots.txt. Các lỗi khác vẫn
    được báo; nếu có quy tắc loại trừ endpoint, truy vấn sẽ bị từ chối.
    """
    global API_CLIENT
    if API_CLIENT is None:
        RAW.mkdir(parents=True,exist_ok=True)
        API_CLIENT=c.Client('cellphones_api',config={'base':'https://api.cellphones.com.vn','delay':2},
                            allow_missing_robots=True)
        policy=API_CLIENT.robots
        snapshot=policy.get('text') or ('HTTP '+str(policy['http_status'])+' tại '+policy['url'])
        (RAW/'robots.txt').write_text(snapshot,encoding='utf-8')
        if not API_CLIENT.permitted(ENDPOINT):
            raise PermissionError('robots.txt không cho phép truy vấn endpoint danh mục')
    return API_CLIENT

def product_row(item,meta,slug,label):
    """Chuyển một sản phẩm API thành bản ghi cùng cấu trúc với crawler HTML.

    Ưu tiên giá hiển thị, sau đó giá khuyến mãi hoặc giá thường nếu thiếu.
    Lọc tên, giá và danh mục; gắn khu vực giá, URL và thông tin minh chứng.
    Trả None nếu sản phẩm không đạt các điều kiện lọc.
    """
    g=item.get('general') or {};f=item.get('filterable') or {}
    name=g.get('name','')
    path=g.get('url_path') or (g['url_key']+'.html' if g.get('url_key') else '')
    if not path:return None
    url=urljoin('https://cellphones.com.vn/',path)
    if urlsplit(url).netloc!='cellphones.com.vn':return None
    price=c.money(f.get('display_price'))
    if not price:price=c.money(f.get('special_price')) or c.money(f.get('price'))
    if not price or not 1000<=price<=2_000_000_000 or len(name)<4 or c.NON_TECH.search(name):return None
    # Xác định nhóm từ metadata danh mục đi cùng sản phẩm trong phản hồi API.
    categories=g.get('categories') or []
    matching=[cat for cat in categories if cat.get('uri','').split('/')[0] in c.TECH_ROOTS['cellphones']]
    if not matching:return None
    root=matching[0];root_slug=root['uri'].split('/')[0]
    manufacturer=g.get('manufacturer') or ''
    # Trường hãng thiếu hoặc chỉ là mã số thì thử nhận diện từ tên sản phẩm.
    brand=manufacturer if isinstance(manufacturer,str) and not manufacturer.isdigit() else ''
    return {'name':name,'product_url':c.norm(url),'sale_price_vnd':price,
            'list_price_vnd':c.money(f.get('display_root_price')) or c.money(f.get('price')),
            'availability':str(f.get('stock_available_id','')),
            'extraction_method':'Public catalog GraphQL query','brand':brand or c.guess_brand(name),
            'source':'cellphones','category_context':c.GROUPS.get(root_slug,root.get('name',label)),
            'category_context_slug':root_slug,'category_context_verified':True,
            'currency':'VND','price_region':'Ho Chi Minh (province_id=30)',
            'crawled_at':meta['fetched_at'],'source_page_url':'https://cellphones.com.vn/'+slug+'.html',
            'evidence_sha256':meta['sha256'],'evidence_file':meta['raw_file'],
            'listing_id':hashlib.sha256(('cellphones|'+c.norm(url)).encode()).hexdigest()[:24]}

def collect_catalog(db,target,max_pages):
    """Duyệt danh mục và phân trang, ghép các niêm yết mới vào SQLite.

    Bảo toàn các mã danh mục đã phát hiện khi tiếp tục đợt chạy. Dừng nguồn
    nếu HTTP 403/429; không báo đạt mục tiêu khi dữ liệu thực tế còn thiếu.
    """
    if c.listing_count()>=target:
        print('Dữ liệu đã đạt ngưỡng; xuất lại kết quả hiện có.',flush=True)
        return
    ensure_api_client()
    discovered_path=RAW/'discovered_category_ids.json'
    discovered=json.loads(discovered_path.read_text(encoding='utf-8')) if discovered_path.exists() else {}
    for category,slug,label in ROOTS:
        previous_fingerprint=None
        for page in range(1,max_pages+1):
            if c.listing_count()>=target:break
            try:
                meta,data=fetch(query_page(category,page))
            except Exception as error:
                c.record_error('api_danh_muc','cellphones',error)
                if isinstance(error,(urllib.error.HTTPError,PermissionError)):
                    if isinstance(error,PermissionError) or error.code in (403,429):raise
                break
            products=data['data']['products'];new=0
            fingerprint=tuple((item.get('general') or {}).get('product_id') for item in products)
            if products and fingerprint==previous_fingerprint:
                c.record_error('phan_trang','cellphones','API lặp lại trang trước; dừng danh mục '+str(category))
                break
            previous_fingerprint=fingerprint
            with db:
                for item in products:
                    row=product_row(item,meta,slug,label)
                    if not row:continue
                    before=db.total_changes
                    # Khóa website + URL giúp giữ một niêm yết duy nhất tại nguồn.
                    db.execute('INSERT OR IGNORE INTO listings VALUES(?,?,?)',('cellphones',row['product_url'],json.dumps(row,ensure_ascii=False)))
                    new+=db.total_changes-before
                    for cat in (item.get('general') or {}).get('categories',[]):
                        if cat.get('uri') in c.TECH_ROOTS['cellphones']:
                            discovered[cat['uri']]=cat['categoryId']
            discovered_path.write_text(json.dumps(discovered,ensure_ascii=False,indent=2),encoding='utf-8')
            print(json.dumps({'category':category,'page':page,'returned':len(products),'new':new,
                              'total_unique':c.listing_count()},ensure_ascii=False),flush=True)
            if len(products)<50:break
        if c.listing_count()>=target:break

def main(argv=None):
    """Bấm Run là tự tạo thư mục, kiểm tra API, thu thập rồi xuất dữ liệu.

    File collect_market_data.py phải đặt cạnh file này để dùng chung hàm
    chuẩn hóa và lưu trữ; không cần bất kỳ dữ liệu hoặc mã hỗ trợ nào khác.
    """
    global RAW, API_CLIENT
    if hasattr(sys.stdout,'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    parser=argparse.ArgumentParser(description='Tự bổ sung niêm yết CellphoneS và xuất dữ liệu chung.')
    parser.add_argument('--target',type=int,default=TARGET)
    parser.add_argument('--max-pages',type=int,default=250,help='Số trang API tối đa mỗi danh mục')
    parser.add_argument('--output-dir',help='Dùng cùng thư mục với collect_market_data.py')
    parser.add_argument('--export',action='store_true',help='Chỉ xuất dữ liệu đã có')
    args=parser.parse_args(argv)
    if args.target<1 or args.max_pages<1:
        parser.error('--target và --max-pages phải là số dương')
    c.configure_output(args.output_dir)
    RAW=c.DATA/'public_api';RAW.mkdir(parents=True,exist_ok=True)
    API_CLIENT=None
    print('Thư mục dữ liệu: '+str(c.DATA),flush=True)
    db=c.connect()
    failed=False
    try:
        if not args.export:
            collect_catalog(db,args.target,args.max_pages)
    except KeyboardInterrupt:
        print('Đã dừng theo yêu cầu; dữ liệu thu được vẫn được xuất.',flush=True)
        failed=True
    except Exception as error:
        c.record_error('khoi_dong_api','cellphones',error)
        failed=True
    finally:
        try:
            stats=c.export_data(db,target=args.target)
        finally:
            db.close()
    print(json.dumps(stats,ensure_ascii=False,indent=2),flush=True)
    print('File CSV: '+str(c.DATA/'market_listings.csv'),flush=True)
    if failed:return 1
    if not args.export and not stats['target_reached']:
        print('Chưa đạt ngưỡng '+str(args.target)+'; xem summary.json và errors.jsonl. Không tạo thêm dòng giả.',file=sys.stderr)
        return 2
    return 0

if __name__=='__main__':
    raise SystemExit(main())
