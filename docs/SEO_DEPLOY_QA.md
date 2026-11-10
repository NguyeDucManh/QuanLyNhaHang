# SEO và chuẩn bị Pull Request Render — 10/11/2026

## Những gì được triển khai trong mã nguồn

- Danh sách công khai duy nhất: `/`, `/menu/`, `/menu/<id>/`, `/about/`, `/offers/`, `/combos/`.
  Title/description riêng, canonical bỏ query, Open Graph/Twitter Card và ảnh chia sẻ tuyệt đối.
- Django Sitemap dùng các route trên và món đang phục vụ trong danh mục active; có lastmod thật
  cho món. Không đưa login, đăng ký, cart, booking, tài khoản, admin, staff, thanh toán/API vào XML.
- Canonical và sitemap dùng `SEO_SITE_URL` đã xác thực HTTPS origin, không lấy Host header để tạo URL.
  Giữ URL `/menu/<id>/` đang hoạt động; không đổi slug hoặc migration để tránh phá link cũ.
- `X-Robots-Tag: noindex, nofollow, nosnippet` cho mọi response ngoài allowlist, biến thể tìm kiếm/lọc,
  response lỗi và redirect. Template customer cũng có meta robots. Không bỏ xác thực, CSRF hoặc RBAC.
- robots.txt cho crawl khi indexing bật, chỉ rõ sitemap và cho phép static; không dùng robots.txt
  làm bảo mật hoặc thay thế noindex. Không chặn bot đọc noindex ở login/cart. Quyền truy cập riêng tư
  vẫn do ứng dụng bảo vệ. Môi trường local/staging mặc định chặn indexing.
- JSON-LD `WebSite`, `BreadcrumbList`, `Menu`, `MenuItem` theo nội dung hiển thị;
  `Restaurant` chỉ khi có RestaurantInfo active. Giá chưa niêm yết không phát sinh Offer;
  không tạo rating, review, priceRange hoặc lịch mở cửa theo ngày chưa có nguồn dữ liệu.
  Nội dung quản trị nhập được escape trước khi đặt trong script, chống đóng thẻ script.
- 404 độc lập context processors/database; 500 độc lập CSS/DB. Giữ status 404/500 thật,
  noindex và không tiết lộ lỗi nội bộ. Không giả HTTP 200 cho trang lỗi.
- Ảnh hero 1536×1024 được chuyển từ PNG 2.442.315 byte thành WebP **239.622 byte**,
  giảm khoảng 90,2%. CSS dùng ảnh mới, preload hero trên home; PNG gốc được giữ lại.
  Ảnh món có alt, width/height, decoding async; ảnh dưới fold lazy, ảnh chi tiết ưu tiên cao.
- Home giữ context gợi ý bằng SimpleLazyObject: template chỉ dùng link sẽ không gọi recommender.
  Trang gợi ý và các mô hình AI vẫn giữ nguyên; không train/download trong startup.
- Tên truy cập cho nút hỗ trợ, link đăng nhập và link giỏ món trên mobile được bổ sung sau audit.
  Không gỡ CSS/JS khi chưa xác minh được tác động tới các chức năng dùng chung.
- Kiểm tra checkout sạch phát hiện max=100 trong form đặt bàn nhanh cũ, trong khi BookingForm/service
  chỉ chấp nhận 1–20. HTML được đồng bộ max=20, không thay đổi quy tắc hoặc dữ liệu nghiệp vụ.
- Schema không xuất hồ sơ nhà hàng có nhãn DEMO, email mẫu `.example`/demo hoặc điện thoại toàn số0;
  dùng cùng quy tắc hiển thị hiện hữu. Không sửa bản ghi để đạt kết quả kiểm thử.

## Cấu hình và quy trình chủ tài khoản

Các biến mới:

| Biến | Cách dùng |
| --- | --- |
| `SEO_SITE_URL` | HTTPS origin chuẩn; production đặt `https://smart-restaurant-demo.onrender.com`, không có path/query |
| `SEO_INDEXING_ENABLED` | Production muốn index đặt true; preview/staging đặt false. Local mặc định false |
| `GOOGLE_SITE_VERIFICATION` | Nội dung token HTML verification từ Search Console, tùy chọn; chỉ render ở home |

Không đưa `.env` vào Git. SEO không đổi model hoặc migration, không cần seed/migrate DB.
Chỉ deploy **sau khi chủ repository duyệt và merge PR**. Không dùng nhánh PR làm production trước duyệt.

1. Review PR, CI/QA. Kiểm tra Auto-Deploy của service: nếu cần triển khai thủ công theo trình tự này,
   chuyển Off trước merge để không chạy cấu hình cũ ngay khi main thay đổi. Tự merge khi chấp thuận.
2. Mở Web Service Render hiện có, xác nhận repository `NguyeDucManh/QuanLyNhaHang`, branch main,
   Root Directory chứa manage.py. Không tạo Web Service hoặc PostgreSQL mới.
3. Trong Settings đặt Build Command `bash build.sh` và Start Command:
   `daphne -b 0.0.0.0 -p $PORT restaurant_system.asgi:application`.
4. `.python-version` khóa Python 3.14.8 đã dùng local; biến `PYTHON_VERSION` trong Environment nếu có
   ưu tiên hơn file, cần khớp. Kiểm tra log cài wheel Linux; chưa chứng minh clean Linux build thành công.
5. Đặt DJANGO_DEBUG=false, giữ đúng DB URL/credentials và cấu hình proxy/host/CSRF theo RENDER_DEPLOY.md;
   bổ sung các biến SEO phía trên. Không in khóa ra log. Không chạy seed/migrate tự động.
6. Đặt Health Check Path `/healthz/`, chọn Manual Deploy → Deploy latest commit sau merge;
   nếu nghi build cache cũ thì dùng Clear build cache & deploy. Đối chiếu SHA ở Events/Build log.
7. Kiểm tra collectstatic thành công, runtime Daphne, health DB và HTTP static sau restart.

## Kiểm chứng sau deploy

Mở DevTools Network/Console trên desktop/mobile; refresh cứng, kiểm tra CSS/JS/ảnh đúng MIME/200,
không phóng to icon; thử menu mobile, tìm món, login, đăng ký, cart, booking và phân quyền.
Không tạo booking/thanh toán production để QA khi chưa được chủ hệ thống duyệt.

Chạy từ bản source trùng SHA đã deploy:

```sh
python scripts/seo_http_qa.py --base https://smart-restaurant-demo.onrender.com --out artifacts/seo-production-after.json
python scripts/render_http_qa.py --base https://smart-restaurant-demo.onrender.com --out artifacts/production-http-after.json
```

Để kiểm tra toàn bộ manifest, chạy verify_static_http từ đúng build có staticfiles.json,
không dùng manifest Windows/local khác hash với Linux production:

```sh
python scripts/verify_static_http.py --base https://smart-restaurant-demo.onrender.com --out artifacts/production-static-after.json
```

Yêu cầu: home/menu/detail/robots/sitemap 200; canonical/og:url cùng HTTPS domain;
XML không có URL riêng tư; login/cart có noindex; món inactive không có trong sitemap/schema.
Django tự đặt X-Robots-Tag noindex cho tài liệu sitemap XML; điều này không ngăn đọc sitemap
để phát hiện URL HTML. Kiểm tra redirect HTTP→HTTPS một lần, không lặp, và CSRF form thật.

Mở [Schema Markup Validator](https://validator.schema.org/) để kiểm tra cú pháp/schema,
[Rich Results Test](https://search.google.com/test/rich-results) để kiểm tra tính đủ điều kiện
cho loại rich result Google hỗ trợ; Menu/MenuItem không đồng nghĩa được rich result.
Chạy PageSpeed Insights mobile/desktop sau deploy; không suy điểm production từ localhost.

## Google Search Console

Vì không sở hữu DNS onrender.com, dùng **URL-prefix property** với URL HTTPS đầy đủ của website.
Chọn HTML tag verification, lấy giá trị content, đặt GOOGLE_SITE_VERIFICATION trong Render Environment,
redeploy rồi xác minh. Không đặt mã HTML hoàn chỉnh vào biến này.
Nếu dùng custom domain và quản lý DNS, có thể chọn Domain property theo hướng dẫn Google.

Sau xác minh: gửi sitemap.xml trong Sitemaps; dùng URL Inspection → Test live URL cho home,
menu và một món thật. Kiểm tra Google-selected canonical, Page indexing/Crawl stats và Core Web Vitals.
Có thể request indexing sau khi trang hoạt động, nhưng Google quyết định thời điểm/chấp nhận indexing.
Không có quyền Search Console trong phiên làm việc này; chưa xác minh ownership hoặc indexing.

## Bằng chứng thực tế và giới hạn

Lượt đầu 15/15 test SEO trên PostgreSQL test riêng PASS; kiểm tra canonical/Host spoofing, query noindex,
sitemap active filter, unpriced/absent restaurant schema, script injection, HTTP lỗi, CSRF,
proxy HTTPS và lazy AI. Sau bổ sung regression placeholder, SEO có 16 test.

**Kết quả cuối:** 606/606 test PASS trên checkout sạch commit `20d0929` (493.892 giây,
`--parallel 2`, PostgreSQL test riêng và hai DB clone); không có test bị bỏ qua.
Sau chỉnh thuộc tính HTML max khách=20, 26/26 test SEO/production tập trung PASS trên `a4e04c4`
(5.229 giây). Đây là lượt chạy lại 26 test trong bộ trên, không cộng thành 632 test khác nhau.

Lượt full đầu 605 test có 1 failure do JSON-LD lộ thông tin DEMO mà UI đã ẩn. Đã sửa schema,
thêm regression và chạy lại toàn bộ thành công; không nới assertion cũ hoặc sửa DB.
Log lỗi cũ: artifacts/pr-clean-test-before-placeholder-fix.log; log cuối: artifacts/pr-clean-test.log
và artifacts/pr-final-focused-tests.log.

Checkout sạch tại `artifacts/pr-review`, đầu tiên tại commit fa55837, đã qua check, check --deploy (3 warning cũ),
makemigrations --check và collectstatic. **233/233 asset** của checkout sạch trả HTTP200 đúng MIME;
workspace hiện tại có thêm hai asset chưa commit của người dùng nên số đếm là 235, không nhầm hai nguồn.
Log: artifacts/pr-clean-static-http.json. Home/menu/about/offers/combos/robots/sitemap/detail thật
đều 200; private login/cart có noindex; sitemap local dùng domain production chuẩn.
Chi tiết: artifacts/pr-clean-seo-http.json và pr-clean-pages-http.json.

Lighthouse 13.6.0 đã chạy local mobile: Performance 88, Accessibility 90, Best Practices 100, SEO92;
LCP 3,7s, CLS0, TBT0ms trong lượt đo. Đây là lab trên máy phát triển trong lúc QA,
**không phải điểm Render, không phải field CWV hoặc INP**. Audit robots timeout do fetch phụ không
đi qua header reverse-proxy localhost; HTTP robots và XML đã được kiểm tra riêng.
Sau sửa, Lighthouse đã được chạy lại trên checkout sạch commit 20d0929: Performance85,
Accessibility100, Best Practices100, SEO92. Audit robots vẫn timeout trong mô phỏng proxy local;
đây là kết quả đo riêng, không phải điểm production.
Log gốc: artifacts/seo-lighthouse-home-mobile.json.
Log lượt clean sau sửa: artifacts/pr-clean-lighthouse-home-mobile.json.

Chrome home ở 320/375/390/768/1024/1440 px sau SEO: đúng font, không overflow,
menu toggle hoạt động, 0 JS exception. Checkout sạch cũng đã kiểm tra home/menu/login/register/cart,
redirect booking và snapshot admin/staff tại sáu kích thước trên; không overflow/lỗi JS/asset lỗi.
Snapshot được render trong transaction chỉ đọc, không chứng minh browser E2E có đăng nhập/ghi dữ liệu.
Form booking đầy đủ có xác thực chưa được browser E2E production; luồng nghiệp vụ có automated tests.
Ảnh local tại artifacts/pr-clean-browser; báo cáo có thể xem trong PR:
[static HTTP](qa/static-http.json), [browser](qa/browser-summary.json), [SEO HTTP](qa/seo-http.json).

Production trước merge vẫn trả 404 cho 8 asset được kiểm tra. robots/sitemap/metadata mới chưa deploy;
chưa có quyền Render Dashboard, log build, DB production hoặc Search Console. Không khẳng định đã sửa
production, đã index Google, đã đạt field Core Web Vitals hoặc mọi nghiệp vụ browser E2E đã qua.

Nguồn chính thức: [Render Python runtime](https://render.com/docs/python-version),
[Render Django static setup](https://render.com/docs/deploy-django),
[Django sitemaps](https://docs.djangoproject.com/en/6.0/ref/contrib/sitemaps/),
[Google robots/noindex](https://developers.google.com/search/docs/crawling-indexing/robots/intro),
[Google structured data](https://developers.google.com/search/docs/appearance/structured-data/intro-structured-data),
[Search Console](https://developers.google.com/search/docs/monitor-debug/search-console-start).
