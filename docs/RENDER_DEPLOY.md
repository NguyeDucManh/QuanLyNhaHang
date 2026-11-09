# Triển khai Smart Restaurant lên dịch vụ Render hiện hữu

Ngày kiểm tra: 10/11/2026 (Asia/Saigon). Không tạo dịch vụ hoặc database mới bằng Blueprint.
Giữ Django 6.1.1, PostgreSQL và Channels. Không chạy seed, migration hoặc train trong startup.

## Mã nguồn và lệnh

Điểm xuất phát local: `main`, `f5ed57e30e53515c07e3e02093d464086cc15865`.
Nhánh chuẩn bị: `fix/render-production-readiness`. Workspace có thay đổi từ trước;
kiểm tra toàn bộ diff trước khi đưa lên GitHub. Chưa xác minh SHA production hoặc cấu hình Render Dashboard.

Trong Web Service hiện hữu, kiểm tra repository, branch, Root Directory (thư mục chứa manage.py),
Build logs và Events để đối chiếu commit trước khi sửa cấu hình:

```sh
# Build Command
bash build.sh
# Start Command (một process ASGI; Render mở rộng biến PORT)
daphne -b 0.0.0.0 -p "$PORT" restaurant_system.asgi:application
```

Python local đã kiểm tra: 3.14.8. Chọn runtime tương thích các phiên bản khóa trong requirements;
chưa có kết quả cài sạch Linux/Render nên phải kiểm tra build log, wheel availability và disk/RAM thực tế.
`requirements-production.txt` bao gồm requirements gốc, WhiteNoise và Redis backend.
Build chỉ cài dependency, system check và collectstatic; lỗi manifest làm build dừng.

Health Check Path: `/healthz/` (SELECT 1; lỗi DB trả 503, không tiết lộ chi tiết).
Static dùng `STORAGES` và WhiteNoise ngay sau SecurityMiddleware; collectstatic phải chạy với DEBUG=false.

## Biến môi trường (chỉ tên, không có bí mật)

| Nhóm | Tên biến |
| --- | --- |
| Django | `DJANGO_SECRET_KEY`, `DJANGO_DEBUG`, `DJANGO_EXTRA_ALLOWED_HOSTS`, `DJANGO_CSRF_TRUSTED_ORIGINS` |
| Render cung cấp | `RENDER`, `RENDER_EXTERNAL_HOSTNAME`, `PORT`, `PYTHON_VERSION` |
| PostgreSQL | `DATABASE_URL` hoặc `DB_NAME`, `DB_USER`, `DB_PASSWORD`, `DB_HOST`, `DB_PORT` |
| Channels | `CHANNEL_REDIS_URL` |
| Stripe TEST | `STRIPE_SECRET_KEY`, `STRIPE_PUBLISHABLE_KEY`, `STRIPE_WEBHOOK_SECRET`, `STRIPE_PUBLIC_BASE_URL` |
| Cọc | `BOOKING_DEPOSIT_REQUIRED`, `BOOKING_DEPOSIT_TYPE`, `BOOKING_DEPOSIT_VALUE`, `BOOKING_DEPOSIT_MINIMUM`, `BOOKING_DEPOSIT_TIMEOUT_MINUTES` |
| Chính sách có sẵn | `BOOKING_HOLD_MINUTES`, `FACEID_DEFAULT_THRESHOLD`, `FACEID_REQUIRE_LIVENESS`, `LOYALTY_VND_PER_POINT`, `FOOD_COST_WARNING_PERCENT` |
| Kiểm thử riêng | `DB_TEST_NAME` |

Render bắt buộc `DJANGO_DEBUG=false` (code từ chối true trên Render).
Tạo SECRET_KEY ngẫu nhiên đủ mạnh trong hệ quản lý bí mật; không ghi vào Git hoặc log.
Local hiện còn cảnh báo SECRET_KEY yếu; không dùng khóa local đó cho production.
`DATABASE_URL` ưu tiên hơn DB_*; chỉ chấp nhận PostgreSQL. Dùng Internal Database URL của đúng DB
cùng region nếu phù hợp; External URL phải tuân thủ SSL/access policy trong Dashboard, không tự bỏ SSL.
Không có fallback SQLite. Connection không giữ lâu để phù hợp ASGI.

Hostname production được cho phép chính xác; hostname thêm dùng danh sách phân cách dấu phẩy,
không thêm `*`, scheme hoặc đường dẫn. CSRF origins phải có `https://`.
`STRIPE_PUBLIC_BASE_URL` đặt thành `https://smart-restaurant-demo.onrender.com`.
Render trusted proxy bật X-Forwarded-Proto; kiểm tra không lặp redirect.
Secure cookies, nosniff, HTTPS redirect và HSTS một giờ bật khi DEBUG=false.
Không bật HSTS includeSubDomains/preload khi chưa xác nhận quyền sở hữu mọi subdomain;
hai cảnh báo deploy tương ứng được giữ nguyên để người vận hành đánh giá.

## Database, migration và seed an toàn

Trước hết xác minh dịch vụ đang trỏ đúng DB trong Environment; không in URL có mật khẩu ra log.
Tạo backup/snapshot PostgreSQL và xác minh có thể khôi phục trước mọi thay đổi schema/data.
Trong Shell của dịch vụ hiện hữu:

```sh
python manage.py check
python manage.py check --deploy
python manage.py showmigrations
python manage.py makemigrations --check --dry-run
python manage.py migrate --plan
python manage.py audit_render_data
```

Chỉ sau khi chủ hệ thống duyệt migration plan và backup:

```sh
python manage.py migrate --noinput
```

Bản sửa này không thêm/sửa model hoặc migration. Không reset schema, không tạo superuser tự động.
`audit_render_data` chỉ đọc số lượng, filter hiển thị và ID ảnh thiếu, không xuất dữ liệu cá nhân.
Nếu có dữ liệu mà UI trống, đối chiếu `visible_menu`, category active, món available,
thời gian promotion, database đang dùng và migrations trước khi seed.

Chỉ khi chủ hệ thống phê duyệt, sau backup và kiểm tra ID/slug, mới chạy các lệnh sau:

```sh
python manage.py seed_menu
python manage.py seed_restaurant
python manage.py audit_render_data
```

seed_menu thêm món còn thiếu theo catalog 45 món, dừng/rollback khi trùng ID tên hoặc slug khác tên;
không ghi đè chỉnh sửa hiện hữu. seed_restaurant thêm khu/bàn/NCC/nguyên liệu thiếu,
không tạo đơn, hóa đơn, giao dịch hoặc tồn kho. Không tự seed promotion/review giả.

## Stripe TEST và WebSocket

Trong Stripe Dashboard chế độ TEST, đăng ký endpoint HTTPS:
`https://smart-restaurant-demo.onrender.com/stripe/webhook/`.
Dùng signing secret của endpoint này, không dùng secret Stripe CLI local. Chọn các event code xử lý:

- `checkout.session.completed`
- `checkout.session.async_payment_succeeded`
- `checkout.session.async_payment_failed`
- `checkout.session.expired`
- `payment_intent.payment_failed`

Chạy `python manage.py check_stripe_config` để kiểm tra cấu hình an toàn.
Redirect success không xác nhận đã cọc. Chỉ webhook hợp lệ mới xử lý; code kiểm tra chữ ký,
livemode=false, owner/metadata, session, amount/currency, idempotency và cọc quá hạn.
Các test ký fixture là kiểm thử hợp đồng, không phải bằng chứng thanh toán thật trên Stripe TEST.
Chạy checkout thực tế bằng tài khoản QA trên môi trường test riêng; không tạo booking/giao dịch
production để kiểm thử khi chưa có phê duyệt.

Không có Redis: chỉ một process Daphne và một instance. Không dùng nhiều worker hoặc scale ngang.
Có nhiều process/instance: cấu hình CHANNEL_REDIS_URL của Redis được phê duyệt trước;
kiểm tra WSS, đăng xuất/thu hồi quyền và fanout giữa instances. Khi rolling deploy, InMemory
không truyền event giữa process cũ/mới; cần refresh hoặc Redis để không mất thông báo.
Lập lịch `python manage.py expire_booking_deposits` riêng theo khả năng tài khoản,
không chạy vòng lặp trong web startup; kiểm tra Stripe/network lỗi trong log.

## AI, file bền vững và giới hạn hạ tầng

FaceNet đang lazy-load qua engine cache; thiếu manifest/model báo ValidationError.
RAG dùng embedding local, không tự download trong request và không phải LLM sinh câu trả lời.
Không train/download pretrained trong build.sh/start command. Torch, ONNX, OpenCV, embedding và
forecast có thể vượt RAM gói nhỏ; chưa đo RAM/timeout trên Render nên chưa xác nhận gói hiện tại đủ.
Cần benchmark thực tế và chọn tài nguyên phù hợp, giữ nguyên tính năng AI.

Các model hiện không có FileField/ImageField upload; ảnh menu tham chiếu static trong repository.
Các artifact AI/index/pretrained trên filesystem và đường dẫn local trong manifest cần kiểm tra
khi sang Linux. Không đặt đường dẫn Windows vào manifest production. Artifact phát sinh không
bền trên filesystem Render tạm: dùng disk/storage đã duyệt, backup và thiết lập đường dẫn phù hợp
trước khi tạo artifact trên production. Không đổi dữ liệu hoặc di chuyển file hiện hữu tự động.
Không phục vụ dữ liệu khuôn mặt/private uploads bằng WhiteNoise.

## Xác minh và rollback

Sau deploy kiểm tra Events SHA, Build log collectstatic, runtime log Daphne, `/healthz/`,
HTTP 404/500, redirect HTTPS, cookies, CSRF và WebSocket. Mở DevTools Network/Console, cache disabled,
refresh cứng; CSS/JS/SVG/ảnh/font chính phải 200 đúng MIME. Asset hash mới tránh cache cũ.
Kiểm tra desktop/mobile, menu, login, booking, staff/admin và Stripe webhook delivery trong Dashboard.
Không ghi khóa, mật khẩu hoặc nội dung nhạy cảm vào log/chụp màn hình.

Lỗi deploy: chọn lại deployment/commit đã hoạt động trong Render Events và redeploy;
giữ nguyên DB và secrets phù hợp. Không chạy migration ngược mù quáng;
nếu schema/data đã đổi cần plan rollback được duyệt và backup đã kiểm tra.

Tham khảo: [Django static deployment](https://docs.djangoproject.com/en/6.0/howto/static-files/deployment/),
[WhiteNoise Django integration](https://whitenoise.readthedocs.io/en/stable/django.html).
