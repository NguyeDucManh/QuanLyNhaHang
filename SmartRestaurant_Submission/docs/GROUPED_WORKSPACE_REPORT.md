# Bố cục theo nhóm chức năng và nhãn vận hành

Cập nhật 15/10/2026, Asia/Saigon. Tiếp tục project Django/PostgreSQL hiện hữu. Không sửa model/migration, booking/HR/order/payment services, thuật toán AI, weights, FaceID/GPS hoặc tests cũ. Timestamps trong evidence giữ theo clock môi trường kiểm chứng.

## 1. Staff dashboard

Bốn khu vực: **Tổng quan hôm nay**, **Ca làm & chấm công**, **Công việc**, **Cá nhân & thu nhập**. Hero giữ danh tính, chức vụ, mã và trạng thái hiện tại; giờ vào/ra, giờ xác nhận trong ngày, khung giờ ca, FaceID/vị trí và nút chấm công nằm chung một khối. Lịch chi tiết hôm nay ở accordion. Công việc chỉ có lịch/bếp/đơn/tin nhắn theo quyền; thu nhập có tổng giờ tháng, kỳ lương và tài khoản riêng.

Dashboard không bật camera/GPS. Có embedding không đồng nghĩa đã xác thực khuôn mặt; hồ sơ chưa xác nhận được ghi rõ. Hero ưu tiên trạng thái vào/ra thực tế khi đã chấm công, không chỉ suy từ giờ ca.

## 2. Thông tin trùng đã bỏ

Bỏ hàng bốn metric rời và lưới action lặp toàn bộ sidebar; không tách ca, chấm công, readiness và tin nhắn thành nhiều card cạnh tranh. Tổng giờ tháng chỉ ở thu nhập, tin chưa đọc ở action tin nhắn, lương/tài khoản không lẫn với vận hành. Hero là tóm tắt, accordion giữ chi tiết ca.

## 3. Admin dashboard

Ngay dưới hero có đúng bốn metric: doanh thu hôm nay, đơn hôm nay, bàn sử dụng và đặt bàn hôm nay. Bên dưới là **Kinh doanh** (chart DB, hóa đơn/khách, món trong đơn đã trả), **Vận hành** (đơn chờ/bếp, khách sắp tới, trạng thái bàn và danh sách đơn gọn), **Kho** (cảnh báo và 5 giao dịch gần nhất), **Nhân sự** (nhân viên vận hành, ca/lịch/chấm công), **AI & cảnh báo** (đường dẫn theo quyền). Không có số/microtrend dựng thêm. Bỏ panel tổng hợp lặp số được chèn cuối trang trước đây.

## 4. Workspace đặt bàn trước/sau

Trước: danh sách 13 cột, form khách không có phân nhóm rõ. Sau: /management/bookings/ giữ nguyên URL, form trái và danh sách phải, tỷ lệ 5/7 khi đủ rộng. POST tạo mới yêu cầu add_booking, dùng create_booking hiện hữu; tài khoản khách tùy chọn, auto-assign giữ nguyên. Không tạo quyền mới cho tài khoản. Người thiếu quyền tạo vẫn xem danh sách theo quyền cũ và thấy hướng dẫn.

Form chia thông tin khách, thời gian/số khách, bố trí bàn và ghi chú. Không thêm gán bàn thủ công hoặc dựng trạng thái “Đã đến” khi model không có. Chi tiết/mở đơn/transition tiếp tục dùng URL/service hiện hữu; các transition phụ nằm trong menu thu gọn.

## 5. Tabs và availability

Mặc định quản lý **Hôm nay**; thêm **Sắp tới**, **Lịch sử**, **Đã hủy**. Khách có tab **Đã hoàn thành** riêng, ngoài Sắp tới/Đã hủy/Lịch sử. Sắp tới nhóm theo ngày; lịch sử lọc khoảng ngày, trạng thái, tên/điện thoại và phân trang 15 bản ghi; liên kết phân trang giữ khoảng ngày. Accordion sắp tới gần nhất giới hạn 5, giữ khả năng mở/xem đơn và đường dẫn cũ.

Endpoint GET /booking/availability/ yêu cầu đăng nhập, validate ngày/giờ/số khách bằng fields và booking_window, gọi find_available_table trong transaction với locks hiện hữu. Chỉ trả có/không có bàn; không ghi Booking hoặc giữ chỗ. Không tự tính overlap/capacity tại frontend và không hứa số bàn giả. Khi lưu, service kiểm tra lại toàn bộ.

## 6. Khách hàng đặt bàn và lịch sử

Form trái giữ preorder/topping/combo/voucher và shared cart services. Bên phải có thông tin đã chọn, chính sách, auto-assignment, link lịch sử riêng và tabs. Sau POST thành công có confirmation card dùng ID server lưu trong session, tra lại theo request.user. Lịch sử/accordion chỉ lấy booking của chủ tài khoản; snapshots tên/giá món và liên kết hóa đơn cũ được giữ. Không lộ lịch sử khách khác.

## 7. Responsive và live QA

Kiểm tra 1920×1080, 1366×768, 768×1024, 390×844. Staff quick actions hai cột trên mobile; facts stack và bottom nav giữ nguyên. Workspace stack trên tablet/mobile; bản ghi đặt bàn chuyển thành cards, không ép bảng nhiều cột. Có kiểm tra input nằm trong field/card, không chỉ document overflow.

[Evidence bản cuối](../evidence/grouped_browser_summary.json), [server log](../evidence/ARCHIVE_NOTICE.md). **140 page/viewport checks**, thêm kiểm tra geometry input và chụp workspace toàn trang ở 4 kích thước. Không tràn ngang, không Runtime.exceptionThrown hoặc HTTP error. Bao gồm manager preview/tạo đặt bàn thật qua HTTP UI trên DB QA, tabs, STAFF lịch/chấm công/lương/chat, ADMIN/Manager dashboard/đặt bàn/bàn/đơn/nhân viên và Customer booking/history/combo/ưu đãi. DB QA được xóa trong finally. OSM tiles có ERR_CONNECTION_RESET và request điều hướng có ERR_ABORTED; giữ nguyên trong evidence, không gọi chúng là lỗi JavaScript. Không coi fixture QA hoặc camera/GPS mock là kiểm chứng thực địa.

## 8. Query và audit CRUD

Booking panel select_related user/table/area/order/invoice, prefetch preorder_items và giới hạn 15; recent archive/sắp tới tối đa 5. Test nhiều hàng đạt ngân sách tối đa 4 query cho panel cốt lõi, không tuyên bố toàn request chỉ 4 query. Giờ ngày dùng Attendance đã tải cùng lịch; giờ tháng vẫn aggregate riêng. Recent stock dùng select_related ingredient, một query giới hạn 5. Dashboard HR chỉ đếm operational employees.

Đã xét bàn/khu vực/đơn/kho/nhân viên/ca/lịch/khuyến mãi: giữ list + edit URL riêng khi nghiệp vụ có transitions, kỳ lương đóng, ownership hoặc nhiều dòng. Shared shell/form/table vẫn áp dụng design system; không ghép nhiều form nguy hiểm vào một POST. Workspace tích hợp ưu tiên đặt bàn, nơi phù hợp với luồng tạo và theo dõi.

## 9. Audit và cleanup nhãn

Ban đầu **80 records / 91 trường** chứa DEMO trong business DB. [Before](OPERATIONAL_LABEL_AUDIT_BEFORE.json), [kế hoạch](OPERATIONAL_LABEL_PLAN.json), [audit source](OPERATIONAL_SOURCE_LABEL_AUDIT.json). Source audit phân biệt fixtures/tests/technical keys/docs và labels; không xóa provenance khoa học hoặc cố làm mất mọi chuỗi trong source.

Đã đổi **18 trường tên**: Topping #1–5, Combo #1–4, Promotion #1–4, RestaurantInfo #1, Shift #1–3 và PayrollPeriod #1. Ví dụ “DEMO - Combo bò” → “Combo bò”; không đổi giá/thành phần/PK/FK. Không có collision trên DB này. [Before → after](OPERATIONAL_LABEL_APPLIED.json). Lần apply thứ hai đổi 0 trường: [after](OPERATIONAL_LABEL_AFTER.json).

**67 records / 73 trường còn marker nội bộ**, gồm notes khởi tạo, lịch sử, mô tả, review mô phỏng, hội thoại cũ và 4 Employee chưa xác nhận. Không xóa hoặc suy đoán danh tính. Một Employee đã được người quản lý xác nhận từ trước task được giữ. FaceID vẫn loại hồ sơ chưa xác nhận bằng rule server hiện hữu. [Kiểm tra số lượng/PK/FK](OPERATIONAL_RELATION_VERIFICATION.json) xác nhận không xóa record hoặc đổi liên kết; FaceProfile/FaceEmbedding được giữ.

Command clean_operational_demo_labels mặc định dry-run; --apply mới sửa tên trong whitelist, atomic, lock từng record và full_clean, log before/after; collision cần review, không đặt tên kỳ quặc. DB QA/test cần --allow-test-database rõ ràng. Không đổi Employee, mã voucher, notes audit hoặc raw conversation.

## 10. Lớp hiển thị và seed

operational_text và HTML presentation middleware làm sạch text/label/input hiển thị, ẩn contact placeholder bằng “Chưa cập nhật” hoặc field trống để quản lý cập nhật. Không bịa địa chỉ/email/số điện thoại thật. Script/style/JSON, hidden values, URLs, enum và PK không bị rewrite. Assistant bubble làm sạch tên/marker cũ ở lớp trình bày, không sửa câu trả lời lưu DB hoặc thuật toán RAG.

Review có marker được trình bày là “Đánh giá mô phỏng”, không biến thành review thật. Các nhãn **Dữ liệu thực tế / Dữ liệu mô phỏng / Chỉ số kiểm tra gián tiếp** giữ nguyên. Thanh toán QR vẫn ghi rõ mô phỏng, không nhận là cổng ngân hàng thật. Một legacy string nằm trong data attribute để giữ tương thích test cũ, không xuất hiện trong text người dùng thấy.

seed_module07_operational_data trên DB vận hành giờ chỉ tạo reference catalog tên sạch qua seed_reference; không tự tạo nhân viên, contact/GPS giả, chấm công hoặc review. Nhánh fixture test/QA giữ marker nội bộ và behavior cũ để không làm sai tests.

## 11. Files và tests

Presentation/query: staff_portal.py, context_processors.py, views.py, management_views.py, booking_workspace.py; templates staff/overview_workspace, booking workspace/fields/panel/summary/archive, base wrappers, invoice; workspace.css, booking-workspace.js, dashboard.js, admin/main.js và assistant.js. Labels/command/seed: operational_labels.py, presentation_middleware.py, clean_operational_demo_labels.py, operational_reference_seed.py và seed command. Thêm duy nhất URL availability; mọi URL cũ được giữ.

Giữ **445 tests baseline**, thêm **16 tests**, tổng **461/461 PASS**, runner 189,308 giây (toàn lệnh 220,328 giây). Check, makemigrations --check, migrate --noinput và pip check đều PASS. [Verification](../evidence/test_summary.json), [log](../evidence/ARCHIVE_NOTICE.md). Tests mới kiểm tra dry-run/idempotence/collision/PK-FK, ownership/RBAC, placeholder/provenance/Employee, manager tạo qua service, preview không mutate, pagination và query budget. Không sửa/xóa test cũ. Source/template/static audit đọc 338 files, không có lỗi: [JSON](../evidence/ARCHIVE_NOTICE.md).

## 12. Screenshots và giới hạn

- [Staff desktop](../evidence/grouped-staff.png), [mobile](../evidence/ARCHIVE_NOTICE.md).
- [Admin toàn trang](../evidence/grouped-admin.png).
- [Workspace đặt bàn desktop](../evidence/grouped-booking.png), [mobile](../evidence/grouped-booking-mobile.png).
- [Khách đặt bàn mobile](../evidence/grouped-customer-booking.png).

Các screenshot dùng fixture DB riêng, không giả là dữ liệu thật đã xác minh. No-DEMO được kiểm tra trên innerText của các route/roles đã chạy; technical identifiers và test fixtures vẫn có marker hợp lệ. Không tuyên bố mọi đường dẫn động hoặc mọi free-text người dùng đều đã kiểm tra. Camera/GPS/calibration thật chưa được chứng minh thêm trong task này. Quyền add_booking cần được ADMIN cấp nếu tài khoản quản lý chưa có; không âm thầm nâng quyền.

Bản SmartRestaurant_Submission/ và ZIP đã được cập nhật theo task này, giữ manifest portable và loại .env/.venv/cache/QA logs. Smoke test bản sạch PASS với PostgreSQL tạm: migrate/seed/routes, FaceNet/MediaPipe CPU, embedding và FAISS; DB tạm đã xóa. Không cài mới dependencies trên máy khác. Số đo/checksum lần cập nhật nằm trong submission_audit/grouped_after.json và file .zip.sha256; các số đo trong báo cáo premium ngày 14/10 là snapshot cũ.
