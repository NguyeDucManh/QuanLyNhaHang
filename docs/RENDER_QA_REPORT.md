# Kết quả QA Render — 10/11/2026

## Cập nhật kiểm thử đúng mã Pull Request

Đã kiểm tra lại trên checkout sạch của nhánh `fix/render-production-readiness`, tách khỏi
các thay đổi có sẵn chưa commit trong workspace. Nhánh sửa đã được push lên đúng repository
`NguyeDucManh/QuanLyNhaHang`; chưa merge hoặc triển khai production.

- Full suite tại commit `20d0929`: **606/606 PASS**, 493.892 giây, PostgreSQL test riêng, hai worker.
- Commit cuối phần code `a4e04c4`: **26/26 test tập trung PASS** sau khi đồng bộ HTML max khách=20
  với quy tắc server hiện hữu; Chrome xác nhận max=20 và responsive không tràn ngang.
- **233/233 static assets** của checkout sạch trả HTTP200 đúng MIME khi DEBUG=false/Daphne.
- System check, migration drift check, collectstatic và pip check qua; deploy check vẫn còn
  W005/W009/W021 đã giải thích ở báo cáo trước. Không có migration mới hoặc ghi dữ liệu production.
- Home/menu/detail thật/robots/sitemap và các trang công khai kiểm tra đều 200 local;
  private routes có noindex và giữ nguyên xác thực/CSRF/RBAC.
- Browser kiểm tra home/menu/login/register/cart, redirect booking và snapshot admin/staff tại
  320/375/390/768/1024/1440px: không tràn ngang, không lỗi JS. Booking có xác thực và thao tác ghi
  admin/staff chưa có browser E2E production; snapshot không thay thế luồng tương tác thực.

Chi tiết bổ sung SEO, kết quả Lighthouse local, lỗi placeholder schema đã phát hiện/sửa,
và thao tác chủ tài khoản: [SEO_DEPLOY_QA.md](SEO_DEPLOY_QA.md).
Bằng chứng có trong repository: [static HTTP](qa/static-http.json),
[browser](qa/browser-summary.json), [metadata/sitemap HTTP](qa/seo-http.json).

Các mục tiếp theo là báo cáo lịch sử của lần sửa đầu, giữ nguyên nguồn gốc số đếm 616/235
trên workspace cũ; dùng số đếm 606/233 ở trên khi đánh giá mã sạch trong PR.

## Phạm vi và bằng chứng

Đã sửa và kiểm tra bản local. **Chưa deploy lên Render**; chưa truy cập Dashboard Render/Stripe,
deployment logs, environment hoặc PostgreSQL production. Không xác nhận production đã sửa xong.
Không push/merge, không seed/migrate DB thật, không tạo giao dịch Stripe hoặc thay đổi tài khoản.
README nghiệp vụ được giữ nguyên. Không thêm migration.

Local ban đầu ở main, SHA `f5ed57e30e53515c07e3e02093d464086cc15865`;
nhánh sửa `fix/render-production-readiness`. Có nhiều thay đổi chưa commit trước tác vụ;
chỉ các thay đổi triển khai trong báo cáo này thuộc tác vụ hiện tại.
Commit code local: `473c17c` (22 file); các file đã có thay đổi được stage từng phần
để không đưa thay đổi có sẵn của người dùng vào commit này. Kết quả QA chạy trên toàn workspace
hiện tại, gồm cả thay đổi có sẵn; chưa kiểm thử checkout sạch chỉ chứa commit 473c17c trên Linux.

## Nguyên nhân và kết quả HTTP

Kiểm tra HTTPS production trực tiếp, không chỉ dựa vào ảnh người dùng:
trang chủ 200 HTML, nhưng cả tám URL static chính dưới đây trả **404 text/html**.
Repository thiếu STATIC_ROOT, storage production, middleware phục vụ static và build collectstatic.
Đây là bằng chứng phù hợp với triệu chứng mất CSS/JS/ảnh; cấu hình thực tế của Render vẫn cần đối chiếu.

| URL | Production trước deploy | Local Daphne DEBUG=false sau sửa |
| --- | --- | --- |
| `/` | 200 HTML | 200 HTML |
| `/menu/`, `/login/`, `/register/`, `/cart/`, `/offers/`, `/combos/` | 200 HTML | 200 HTML |
| `/booking/`, `/staff/`, `/management/` chưa đăng nhập | Redirect login, cuối 200 | Redirect login, cuối 200 |
| `/static/customer/css/style.css` | 404 HTML | 200 text/css |
| `/static/ui/design-system.css` | 404 HTML | 200 text/css |
| `/static/ui/reference-match.css` | 404 HTML | 200 text/css |
| `/static/customer/js/main.js` | 404 HTML | 200 text/javascript |
| `/static/admin/css/style.css` | 404 HTML | 200 text/css |
| `/static/ui/staff-pos.css` | 404 HTML | 200 text/css |
| `/static/ui/favicon.svg` | 404 HTML | 200 image/svg+xml |
| `/static/ui/images/garden-restaurant-hero.png` | 404 HTML | 200 image/png |
| `/healthz/` | 404 | 200 application/json, SELECT 1 |
| `/not-found/` | 404 | 404 |

HTTP raw và thời gian đo từng request: `artifacts/render-http-production-before.json`,
`artifacts/render-http-local.json`. Local HTML khoảng 83–248 ms trong lượt đo, không phải benchmark Render.
Các URL static gốc có cache public 60 giây; test URL hash kiểm tra `immutable` và MIME.
Network browser lưu trong `artifacts/render-browser/*/asset-responses.json`.
Đường dẫn có dấu/khoảng trắng được Django encode; catalog local không thiếu ảnh.
Đã đối chiếu toàn bộ tham chiếu `{% static '...' %}` trong templates với tên file có phân biệt
hoa/thường: không phát hiện asset thiếu hoặc sai case; log `render-static-reference-audit.json`.

## Các lỗi được sửa

- settings.py: DEBUG theo môi trường, từ chối DEBUG=true trên Render, hostname/CSRF/proxy,
  secure cookies/HTTPS/nosniff/HSTS, DATABASE_URL PostgreSQL tương thích DB_*, test DB riêng,
  STATIC_ROOT và STORAGES manifest WhiteNoise, middleware đúng thứ tự.
- requirements.txt và requirements-production.txt: bổ sung WhiteNoise, dj-database-url và include dependency gốc.
- build.sh: cài dependency, check, collectstatic; không migrate/seed/train tự động.
- health.py và urls.py: readiness kiểm tra DB, lỗi 503 không tiết lộ nội bộ.
- Leaflet JS: bỏ sourceMappingURL trỏ tới map không tồn tại, vốn làm manifest build thất bại.
- Customer/admin/staff base và staff icons: guard SVG có kích thước/stroke/fill trước khi CSS tải;
  giữ hệ màu/font/layout và thứ tự stylesheet hiện hữu, không gỡ CSS khi chưa có bằng chứng dư thừa.
- menu_service.py và dish-placeholder.svg: ảnh thiếu/rỗng dùng asset dự phòng thật,
  tránh ValueError manifest làm hỏng trang production.
- customer menu/header và admin payments: sửa chữ lỗi mã hóa ở chọn món đặt bàn,
  thành viên và đối soát tiền cọc.
- reference-match.css: native input ngày/giờ không đẩy tràn cột tablet; footer có thể wrap.
- audit_render_data: đếm/read-only các bảng và filter hiển thị; không in PII hoặc credentials.
- test_render_production.py: HTTP/MIME/cache production, fallback ảnh, SVG/tiếng Việt,
  health DB, fail-safe lỗi DB và cấu hình Render/PostgreSQL.
- scripts/render_http_qa.py và render_browser_qa.py: lưu HTTP, screenshot, font,
  chiều rộng, thao tác menu và lỗi JS; không tạo đơn/booking/thanh toán.

## PostgreSQL local

Đã xác minh DB_HOST local; không đại diện cho database Render.

| Bảng | Số lượng |
| --- | ---: |
| Category | 19 |
| MenuItem | 45 |
| Area | 4 |
| RestaurantTable | 20 |
| Combo | 4 |
| Promotion | 4 |
| Review | 2 |
| RestaurantInfo | 1 |
| Supplier | 3 |
| Ingredient | 71 |
| RecipeIngredient | 174 |

45 món thỏa is_available/category active; 4 promotion trong khung thời gian; không thiếu ảnh catalog.
Không seed dữ liệu để đạt kết quả. Chưa biết DB Render có trống hay khác filter/DB URL.
Lệnh chẩn đoán và seed cần chủ hệ thống phê duyệt nằm trong RENDER_DEPLOY.md.

## Trình duyệt và responsive

Edge: home/menu/login/cart tại **320/375/390/768/1024/1440 px**; font Segoe UI,
không Times New Roman sau khi tải xong, không tràn ngang và 0 Runtime.exceptionThrown.
Chrome: home ở sáu kích thước tương tự, menu mở/đóng thành công; phát hiện input giờ tràn
ở 768 px trong lượt đầu và đã sửa. Lượt Chrome sau sửa không tràn ngang, 0 lỗi JS.
Network ghi HTTP status/MIME của CSS/JS/ảnh thực tế; chưa mô phỏng đầy đủ slow network/offline cache.

Admin và staff được render từ dữ liệu local trong **transaction SET TRANSACTION READ ONLY**;
snapshot kiểm tra responsive không thay đổi dữ liệu, không đăng nhập browser bằng tài khoản thật.
Snapshot không chứng minh live WebSocket/control polling hoặc tương tác ghi dữ liệu đã chạy trong browser.
Đối với các phần đó dùng test Channels và kiểm thử nghiệp vụ riêng bên dưới.
Snapshot staff dùng một tài khoản có quyền hạn chế: UI hiển thị trạng thái chưa được cấp quyền
xem bàn/menu; không tự nâng quyền để làm ảnh demo. Cả hai snapshot đều không tràn ngang,
không lỗi JS và không có asset lỗi tại sáu kích thước đã nêu.

Ảnh/bằng chứng local (ignored khỏi Git):

- [Home Chrome mobile](../artifacts/render-browser/chrome-home/home-390.png)
- [Home Chrome desktop](../artifacts/render-browser/chrome-home/home-1440.png)
- [Home Chrome tablet sau sửa](../artifacts/render-browser/chrome-home/home-768.png)
- [Menu mobile](../artifacts/render-browser/menu/home-390.png)
- [Login mobile](../artifacts/render-browser/login/home-390.png)
- [Cart mobile](../artifacts/render-browser/cart/home-390.png)
- [Admin snapshot mobile](../artifacts/render-browser/admin/home-390.png)
- [Staff snapshot mobile](../artifacts/render-browser/staff/home-390.png)

## Kiểm tra tự động

Python 3.14.8, Django 6.1.1, PostgreSQL test riêng; không chuyển sang SQLite.
Lệnh full suite đặt DB_TEST_NAME=test_render_20261110, OMP/OPENBLAS_NUM_THREADS=1,
HF_HUB_OFFLINE/TRANSFORMERS_OFFLINE=1 để không download model.

| Lệnh | Kết quả |
| --- | --- |
| `python manage.py check` | PASS, 0 issues |
| `python manage.py check --deploy` với Render/DEBUG=false | 0 errors, 3 warnings: W005/W009/W021 |
| `python manage.py makemigrations --check --dry-run` | PASS, No changes detected |
| `python manage.py migrate --plan` local, chỉ đọc | PASS, No planned migration operations |
| `python manage.py collectstatic --noinput` DEBUG=false | PASS, 234 static assets, manifest/compression |
| `python -m pip check` | PASS, No broken requirements |
| Regression static/health/template | 5/5 PASS |
| Regression cấu hình Render/DATABASE_URL/test DB | 5/5 PASS |
| Full suite | **616/616 PASS**, 301.329 giây; log `artifacts/render-tests-passing.log` |

Lượt full suite đầu chạy 616 test, có 1 failure và 1 error: assertion hợp đồng DB_PASSWORD
và test mới tự đóng FileResponse làm đóng connection test. Đã sửa: DB_* vẫn yêu cầu mật khẩu
khi không dùng DATABASE_URL; test đọc streaming_content qua test client đúng lifecycle.
Không bỏ test hoặc nới business assertions. Đã chạy lại regression và toàn bộ 616 test thành công.
Năm test cấu hình được bổ sung sau thời điểm full suite discover, chạy riêng và 5/5 PASS;
không cộng chúng thành một lượt full suite 621 test chưa thực sự chạy.
Log gốc giữ ở artifacts/render-tests-final.log và render-regressions.log.

Các test sẵn có bao phủ registration/login/CSRF/RBAC/IDOR, booking capacity/overlap/rollback,
cọc hết hạn/chữ ký webhook/amount/currency/idempotency/success redirect, order/kitchen/invoice,
trừ kho không lặp và concurrency, scheduling/attendance/GPS/payroll/locked state,
AI artifact/privacy và Channels origin/session/permission revocation/chat.
Fixture webhook ký/mocked provider không thay thế checkout Stripe TEST trên Render.

## Chưa xác minh và thao tác chủ tài khoản

Chưa có quyền Dashboard nên chưa kiểm tra branch/SHA production, Build/Start Command hiện tại,
Render logs, DB counts/backup, Redis topology, restart Render, RAM/cold start AI và Linux clean build.
Không kiểm tra thành công checkout Stripe TEST trên domain Render hoặc webhook Dashboard delivery.
Chưa chạy đầy đủ browser E2E có xác thực mọi màn hình admin/staff/payroll/AI.

Chủ tài khoản cần review diff/commit, cấu hình Environment và Build/Start Command theo
[RENDER_DEPLOY.md](RENDER_DEPLOY.md), đặt secret đủ mạnh (W009), xác nhận backup/migration plan,
kiểm tra dữ liệu/seed nếu cần, cấu hình webhook TEST và triển khai commit đã duyệt.
W005/W021 giữ nguyên vì chưa xác nhận domain/subdomain phù hợp HSTS preload.
Sau deploy phải kiểm tra lại HTTPS/Network/cache/login/booking/Stripe/WSS;
chưa đạt acceptance production cho tới khi bước đó hoàn tất.
