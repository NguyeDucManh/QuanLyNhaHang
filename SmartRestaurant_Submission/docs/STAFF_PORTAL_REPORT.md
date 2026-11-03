# Báo cáo nâng cấp giao diện nhân viên Smart Restaurant

Ngày kiểm chứng: 14/10/2026, Asia/Saigon. Tiếp tục Django/PostgreSQL hiện hữu. Báo cáo bổ sung cho [UI_FACEID_VI_REPORT.md](UI_FACEID_VI_REPORT.md).

## 1. Vấn đề trước nâng cấp

Staff dùng chung lớp trình bày khách hàng hoặc quản trị, dashboard ít thông tin cá nhân và chưa có điều hướng công việc rõ ràng. Footer khách hàng lớn không phù hợp màn hình làm việc. Lịch, lương và hội thoại cần cách trình bày dễ đọc trên điện thoại.

## 2. Layout nhân viên

Tạo staff/base và staff/management: sidebar xanh rừng, topbar danh tính, navigation theo quyền, nội dung nền kem và điểm nhấn vàng. Mobile có drawer, backdrop, Escape và bottom navigation. Footer nhỏ nằm trong workspace flex; trang nhân viên không nạp footer lớn của khách hàng. SVG dùng chung, không thêm thư viện icon.

## 3. Dashboard và nguồn dữ liệu

Dashboard lấy Employee liên kết trực tiếp request.user, lịch hôm nay, tình trạng vào/ra, giờ công tháng và lương kỳ hiện tại từ DB. Giờ công chỉ cộng khoảng vào–ra đã kết thúc và được xác nhận. Lương chỉ hiển thị kỳ APPROVED/PAID; chưa có dữ liệu thì trình bày trạng thái trống. Có welcome, mã/chức vụ, ca hiện tại, timeline, quick actions, tin chưa đọc và hướng dẫn chuẩn bị chấm công. Dashboard không tự bật camera/GPS.

Identity được cache theo request; lịch dùng select_related và giờ công dùng aggregate. Test giới hạn phần truy vấn dashboard cốt lõi tối đa 5 query, không tuyên bố toàn bộ request chỉ có 5 query.

## 4. Các trang nâng cấp

Lịch tuần có tuần trước/sau và cards từng ngày; lịch sử chấm công và lương vẫn giữ URL hiện hữu. Chi tiết lương có 7 giá trị tổng hợp. Profile cho phép sửa tên, họ và email của chính tài khoản; không nhận role, username hoặc user_id từ form. Không thêm nút đổi mật khẩu khi chưa có luồng tương ứng.

Chat có danh sách hội thoại, unread, bubbles, avatar và giờ Việt Nam; dùng persistence/WebSocket hiện hữu. Read receipt chỉ cập nhật participant của người đang đăng nhập. Menu/đơn hàng dùng shell nhân viên khi được cấp quyền. Bếp có ba cột chờ/đang làm/sẵn sàng; paginator cũ giữ nguyên, cột sẵn sàng bổ sung tối đa 30 món gần nhất.

## 5. FaceID/GPS và các trang được giữ

Trang chấm công dùng shell nhân viên mới, giữ FaceNet ONNX CPU, cosine/mean embedding/L2, threshold, enrollment, challenge, attendance service và Haversine. Không thay model weights/dependency. Home/menu/cart/booking khách hàng giữ bố cục hiện hữu; shared forms, footer và chat được polish. Manager/Admin tiếp tục dùng index quản trị.

## 6. Audit toàn bộ templates

[STAFF_TEMPLATE_AUDIT.md](STAFF_TEMPLATE_AUDIT.md) phân loại 153 templates theo base, quyết định giữ/nâng cấp và action. Prototype/legacy được ghi riêng và giữ nguyên; audit nguồn không đồng nghĩa mọi template đều có route live hoặc đã thao tác toàn bộ CRUD.

## 7. Components và files

Backend trình bày: customers/staff_portal.py, views.py, module07_views.py, business_views.py và context processors. Templates mới trong templates/staff; shared chat_app/chat_messages và customer/portal_footer. CSS/JS: staff.css, staff-refinements.css, staff.js, product-polish.css. Không có migration mới hoặc thay service nghiệp vụ AI/đặt bàn/đơn/bếp/thanh toán/kho/lương.

## 8. Responsive và footer

Live Edge kiểm tra 10 trang manager và 9 trang staff ở 1920×1080, 1366×768, 768×1024, 390×844: 76 checks không tràn ngang. Thêm 5 trang khách hàng trên mobile. Lịch dùng cards; bếp và chat đổi bố cục; bảng cần thiết có vùng cuộn. Trang dài có cuộn dọc và khoảng chừa bottom navigation. Footer khách hàng lấy thông tin RestaurantInfo thực, không dựng số điện thoại/giờ mở cửa giả.

## 9. RBAC và dữ liệu cá nhân

Navigation chỉ hiển thị theo quyền; backend vẫn kiểm tra quyền. Staff không thấy dữ liệu lịch/chấm công/lương của người khác. Payroll STAFF được scope own kể cả khi có view_payroll; thao tác tính/đổi trạng thái lương yêu cầu ADMIN/MANAGER và permission tương ứng. Profile POST chỉ cập nhật ba field cho request.user. Không đổi User–Employee, tự xác nhận nhãn seed, xóa hồ sơ hoặc chỉnh embeddings trên DB chính.

## 10. Live browser và giới hạn

[Evidence](../evidence/ARCHIVE_NOTICE.md), [server log](../evidence/ARCHIVE_NOTICE.md): DB QA UUID riêng, fixture được tạo bằng service hiện hữu, DB đã xóa trong finally. GPS_ONLY vào/ra thực thi service thật với tọa độ mock; chat gửi qua HTTP và nhận WebSocket; profile form, drawer/bottomnav và confirmation dialog được thao tác trong browser. Không có Runtime.exceptionThrown.

Tiles OpenStreetMap tại settings bị ERR_CONNECTION_REFUSED do mạng; một Document request bị hủy khi điều hướng profile. Evidence giữ nguyên các lỗi mạng này. Camera/GPS là mô phỏng, không chứng minh sensor thật, enrollment thật hoặc biometric accuracy. Không tuyên bố mọi trình duyệt và mọi action đã được kiểm chứng.

## 11. Tests và verification

Giữ 431 tests cũ; thêm 14 tests dữ liệu riêng, lịch tuần, quyền, profile, payroll, unread/read receipt và query budget. **Full regression 445/445 PASS**, runner 162,043 giây, toàn lệnh 171,356 giây. Django check, makemigrations --check, migrate --noinput và pip check PASS. Không sửa/xóa tests cũ để đạt PASS.

[Verification](../evidence/ARCHIVE_NOTICE.md), [full test log](../evidence/ARCHIVE_NOTICE.md). Source audit 326 files không có lỗi tại thời điểm kiểm tra: [source audit](../evidence/ARCHIVE_NOTICE.md). Không cài lại/downgrade stack AI.

## 12. Screenshots và demo

Ảnh live dùng dữ liệu QA riêng, không phải dữ liệu nhân viên đã được xác nhận trên DB chính:

- Dashboard: [desktop](../evidence/ARCHIVE_NOTICE.md), [1920](../evidence/ARCHIVE_NOTICE.md), [tablet](../evidence/ARCHIVE_NOTICE.md), [mobile](../evidence/ARCHIVE_NOTICE.md).
- [Lịch mobile](../evidence/ARCHIVE_NOTICE.md), [lương desktop](../evidence/ARCHIVE_NOTICE.md), [chat desktop](../evidence/ARCHIVE_NOTICE.md), [profile mobile](../evidence/ARCHIVE_NOTICE.md).
- [Menu staff](../evidence/ARCHIVE_NOTICE.md), [bếp](../evidence/ARCHIVE_NOTICE.md), [đơn hàng](../evidence/ARCHIVE_NOTICE.md), [chấm công mobile](../evidence/ARCHIVE_NOTICE.md).

Đăng nhập STAFF → /staff/ → lịch/chấm công/lương/chat/tài khoản; các mục menu/bếp/đơn chỉ hiện khi có quyền. Để vận hành FaceID/GPS thật vẫn cần xác nhận Employee/consent, enrollment đúng người, vị trí/ca thật và kiểm chứng phần cứng/calibration như báo cáo trước.
