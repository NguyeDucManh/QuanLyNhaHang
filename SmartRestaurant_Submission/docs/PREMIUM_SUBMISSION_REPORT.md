# Smart Restaurant — UI premium và source submission sạch

Ngày: 14/10/2026, Asia/Saigon. Phạm vi: trình bày, audit filesystem, cleanup cache đã xác định và tạo bản nộp độc lập. Giữ Django/PostgreSQL, toàn bộ 445 tests, migrations, AI/services và DB chính.

## 1. Vấn đề UI ban đầu

Staff có hero nhạt, nhiều card cùng nền; login có panel ít nội dung; admin metric thiếu phân cấp; customer thiếu sự nối tiếp giữa hero và các section. Source lẫn môi trường, QA lịch sử và cache nên ZIP khó kiểm soát.

## 2. UI đã sửa

Design system bổ sung forest 950–700, champagne gold và cream. Staff/admin có hero gradient đậm, cards màu theo ý nghĩa và icon containers. Login/register dùng ảnh cá hồi static có thật, overlay và split screen; form có focus/error và hiện/ẩn mật khẩu. Customer giữ concept hero, bổ sung serif display, CTA vàng, section gợi ý nền xanh, combo nền ấm, giới thiệu nền forest, footer thống nhất. Bảng có header tint/zebra/hover; animation nhẹ và hỗ trợ reduced-motion. Không thay pipeline FaceID hoặc kích thước guide.

Files chính: static/ui/premium.css, premium.js; ba base templates; customer/auth và home; admin/main.js và ui/dashboard.js. Ảnh cá hồi 900×675 và bò 900×600 sẵn có thay ảnh phóng lớn bị mờ. Full-page review phát hiện lý do recommendation chiếm chiều rộng card; đã đổi compact card sang grid hai cột, lý do nằm dưới nội dung. Không dùng ảnh Internet, tạo frontend mới, thay backend hoặc thêm dependency.

## 3. Screenshot staff

[Desktop](../evidence/premium-staff.png), [1920](../evidence/ARCHIVE_NOTICE.md), [tablet](../evidence/ARCHIVE_NOTICE.md), [mobile](../evidence/ARCHIVE_NOTICE.md). Cards dùng dữ liệu service trong DB QA, không phải dữ liệu vận hành chính.

## 4. Screenshot login/register

[Login desktop](../evidence/premium-login.png), [mobile](../evidence/ARCHIVE_NOTICE.md), [register](../evidence/ARCHIVE_NOTICE.md). Ảnh customer/images/salmon.jpg giữ nguyên path; nút hiện/ẩn mật khẩu không gửi/lưu mật khẩu.

## 5. Screenshot admin

[Dashboard](../evidence/premium-admin.png), [mobile](../evidence/ARCHIVE_NOTICE.md). Doanh thu/đơn/bàn/nhân sự/kho và chart 7/30 ngày giữ nguồn DB hiện hữu; không thêm số hoặc microtrend giả. Role được hiển thị tiếng Việt, enum backend không đổi.

## 6. Screenshot customer và live QA

[Home](../evidence/premium-customer.png), [mobile](../evidence/ARCHIVE_NOTICE.md), [menu](../evidence/ARCHIVE_NOTICE.md), [booking](../evidence/ARCHIVE_NOTICE.md), [assistant](../evidence/ARCHIVE_NOTICE.md). Live Edge: 112 page/viewport checks trên 1920/1366/768/390, không horizontal overflow. Có camera/GPS mock, chat HTTP/WebSocket, profile, drawer, dialog và password toggle. Không Runtime.exceptionThrown hoặc static HTTP error. [Evidence gốc](../evidence/ARCHIVE_NOTICE.md). Request Document bị browser hủy khi điều hướng được giữ trong evidence. Camera/GPS là mô phỏng, chưa chứng minh hardware/biometric accuracy.

## 7. Dung lượng ban đầu

Audit trước UI/cleanup: **1.750.966.907 bytes = 1.669,85 MiB**, 51.223 files. .venv **1.714.890.756 bytes = 1.635,45 MiB**. Đây là dung lượng file trên đĩa; không so trực tiếp với ZIP khoảng 587 MB người dùng nêu. Audit không xóa file.

## 8. Top thư mục/file lớn

[Audit trước](../evidence/BEFORE.md) chứa top 20 directories/files; [JSON đầy đủ](../evidence/ARCHIVE_NOTICE.md) và cleanup_manifest.json phân loại từng item PATH/SIZE/CATEGORY/REASON/ACTION. Số đo sau build được ghi tại evidence/SIZE_REPORT.md và submission_audit/after.json. Project gốc có thể tiếp tục sinh cache khi chạy.

## 9. Cache đã xóa

cleanup_cache.ps1 mặc định dry-run, -Apply mới xóa file CACHE từ manifest. Đã xóa **145 files, 1.771.563 bytes**. Script kiểm tra absolute path trong workspace, tên cache, tránh .venv và reparse point; không có recursive delete và không xóa UNKNOWN. [Cleanup record](../evidence/cache_cleanup.json). Không xóa DB, source, tests, migrations, model hoặc dữ liệu người dùng.

## 10. Chỉ exclude khỏi submission

.venv, .env, QA directories, ai_verification/log dài, screenshot cũ, artifacts screenshots, SQLite cũ, IDE tooling, scripts sửa template một lần và artifact AI version lịch sử. Các file này giữ trên máy; không đồng nghĩa có thể xóa. Bản nộp giữ bốn screenshot mới đại diện và summaries tối thiểu trong evidence. References QA lịch sử trong các report copy được chuyển sang archive notice, không gán bằng chứng mới cho kết quả lịch sử.

## 11. Runtime/source/model bắt buộc giữ

Giữ customers/restaurant_system/templates/static, toàn bộ tests/migrations/commands, requirements, .env.example, README/docs, metadata và latest forecast/recommendation/FAISS/dataset/evaluation. 52 ảnh static không trùng hash, không vượt 1.600px; không resize/nén lại hoặc làm mất 45 ảnh menu. History nghiên cứu và phiên bản cũ giữ ở workspace gốc, chỉ exclude khỏi ZIP.

FaceNet 91.243.099 bytes, MediaPipe 3.758.596 bytes và embedding cache 484.802.094 bytes đang ở D:/SmartRestaurant-AI-cache, ngoài project. Hash FaceNet/MediaPipe và 10 embedding files khớp manifest. Source không copy các cache này. [Model audit](../evidence/model_assets.json) ghi runtime paths, revisions, hashes và latest versions. Manifest copy bỏ đường dẫn D: tuyệt đối, giữ provenance/hash; setup_models cấu hình cache máy mới.

## 12. Bản source sạch

scripts/build_submission.ps1 tạo SmartRestaurant_Submission/ bằng allowlist và kiểm tra path; không ghi đè output có sẵn hoặc xóa project gốc. Source có .env.example và scripts/setup_models.py, verify_submission.py; không cần .venv đóng gói. Kích thước đo thật được cập nhật trong SIZE_REPORT sau build.

## 13. ZIP

SmartRestaurant_Submission.zip dùng ZIP deflate. Có checksum và thống kê file/directory sau build. Không chứa .venv/cache/.env/DB dump/qa_*/log/archive cũ. Không tuyên bố dung lượng giảm hoặc demo offline đầy đủ trước khi đo/setup model.

## 14. Requirements/env và setup

[README](../README.md) và [SUBMISSION_SETUP](SUBMISSION_SETUP.md) có Python 3.14/PostgreSQL, venv, pip requirements, cấu hình .env, migrate, seed_rbac/seed_menu, createsuperuser, model download/reuse cache, rebuild FAISS và runserver. Không mật khẩu demo cố định, không copy SECRET_KEY/password/API key thật. Không cài lại/downgrade stack hiện hữu.

## 15. Regression và clean smoke test

Giữ toàn bộ **445/445 tests PASS**, runner 263,350 giây, toàn lệnh 291,959 giây. Django check, makemigrations --check, migrate --noinput và pip check PASS. [Kết quả](../evidence/ARCHIVE_NOTICE.md), [log](../evidence/ARCHIVE_NOTICE.md). Các pins trong requirements.txt khớp phiên bản đã cài. Source/templates/static audit không có lỗi tại thời điểm kiểm tra. Clean verification dùng PostgreSQL UUID riêng, migrate/seed/routes, CPU FaceNet/MediaPipe, embedding và FAISS; kết quả cuối nằm trong evidence. Không thực hiện fresh pip install trên máy khác; tái dùng interpreter đã chuẩn bị để tránh thay stack. Các chỉnh cuối về ảnh/card/nhãn chỉ ở lớp trình bày và được live QA lại.

## 16. Secrets, bảo toàn và giới hạn

Builder không copy .env, scan nội dung text theo các secret values cấu hình trong RAM, không xuất giá trị secret ra log. ZIP được kiểm tra entries và checksum; smoke test không seed DB chính. Cache model gốc và FaceProfile/embeddings không bị xóa. Để demo offline máy mới, cần tải/chuẩn bị cache đúng hash trước; OSM tiles cần mạng. Vận hành thật vẫn cần consent/enrollment, GPS sensor và calibration như các report trước. Kết quả không chứng minh mọi CRUD hoặc mọi trình duyệt.


### Kết quả build/verification cuối

Source clean: **8.76 MiB**; ZIP: **4.95 MiB**. Số bytes chính xác, top 20 trước/sau và checksum tại submission_audit/after.json. Audit trước 1.669,85 MiB; .venv 1.635,45 MiB được giữ ngoài ZIP.

Clean smoke PASS: migrate/seed/routes, FaceNet ONNX và MediaPipe CPU, embedding CPU inference, FAISS 384 chiều và latest forecast/recommendation. DB QA đã xóa. FAISS verification đọc bytes để hỗ trợ đường dẫn Windows tiếng Việt; không đổi service runtime. Không thực hiện cài mới dependencies trên máy khác. ZIP không chứa secret .env; checksum nằm ở file SHA256 bên cạnh ZIP.
