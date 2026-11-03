# Hướng dẫn demo Smart Restaurant

Phần FaceID đã được cập nhật: ưu tiên [FACEID_OPERATIONAL_REPORT.md](FACEID_OPERATIONAL_REPORT.md). Trước enrollment/chấm công, quản lý cần xác nhận hồ sơ thật theo liên kết User hiện hữu. Recognition mặc định chỉ nhìn thẳng và dùng PROVISIONAL nếu chưa calibrate; liveness bật/tắt theo server settings. Calibration thật vẫn cần cho đánh giá biometric.

## Khởi động

Từ thư mục project, dùng PowerShell:

```powershell
.\.venv\Scripts\python.exe manage.py check
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py runserver 127.0.0.1:8000
```

Mở http://127.0.0.1:8000 bằng Edge/Chrome. Dùng tài khoản hiện hữu đúng vai trò; báo cáo không chứa mật khẩu hoặc nội dung .env. Camera/GPS yêu cầu browser permission; localhost được browser coi là secure context. Khi triển khai host khác cần HTTPS.

## Kịch bản trình bày

1. Customer: home → menu/category/search/price/sort → detail → topping/quantity/cart → booking. Giới thiệu desktop và viewport mobile.
2. Manager: booking/order → kitchen PREPARING/READY → hoàn tất → invoice/payment demo → customer history/review. Nói rõ demo không phải giao dịch ngân hàng thật.
3. Inventory: nguyên liệu/recipe/supplier/nhập-xuất/cảnh báo. Employee: ca/lịch/chấm công/payroll. Chỉ thao tác dữ liệu được phép thay đổi.
4. AI dashboard: GA scheduling, hybrid recommendation, forecast và AI inventory. Giải thích provenance REAL/SYNTHETIC và metric cũ, đặc biệt forecast chưa đủ chính xác vận hành.
5. Assistant: “nhà hàng có gì”, “món từ 300 đến 700k”, chọn “món thứ 2”, “thêm 2 phần”; booking trả lời số khách/ngày/giờ qua nhiều lượt; “hóa đơn của tôi”; câu ngoài dữ liệu để thấy fallback. Dữ liệu menu hiện tại quyết định kết quả.
6. Human support: chat riêng và cập nhật WebSocket. Reports: trình bày số liệu DB và bộ lọc hiện có.
7. FaceID/GIS: làm các bước dưới trước khi khẳng định demo phần cứng thật thành công.

## Chuẩn bị FaceID và GPS thật

1. Manager mở `/management/settings/location/`, đặt tọa độ thật, radius và max accuracy phù hợp; chọn mode, bật policy và lưu. DB chính chưa được tự gán tọa độ/policy giả.
2. Kiểm tra Employee liên kết đúng user, có ca/lịch. Mở danh sách FaceID và trang enrollment của nhân viên; bật webcam, làm theo trước/trái/phải, xem quality, lưu mẫu. Chỉ thu người đã đồng ý.
3. Trang FaceID test: xác minh đúng người/sai người, challenge và ánh sáng/góc mặt; không tạo attendance. Thu dữ liệu genuine/impostor để calibrate threshold, không tự coi mặc định là đã đạt.
4. Nhân viên mở `/work/faceid/`, cho phép GPS/camera khi mode yêu cầu. Kiểm tra bên trong/bên ngoài radius, accuracy thấp, từ chối permission, in/out hợp lệ và audit.
5. FACE_ONLY không cần GPS; GPS_ONLY không cần camera; FACE_AND_GPS cần cả hai. Thiếu cấu hình cần thiết phải từ chối. Không đổi sang GPS_ONLY để che việc FaceID chưa kiểm tra.

Evidence hiện có chỉ chứng minh GPS mock, không sensor thật; webcam/enrollment/calibration thật chưa được kiểm tra. Khi tự kiểm tra, ghi thời gian, thiết bị, mode, kết quả và điều kiện môi trường, tránh lưu ảnh cá nhân trong báo cáo công khai.

## Chạy lại QA độc lập

```powershell
.\.venv\Scripts\python.exe scripts/ai_final_checks.py
.\.venv\Scripts\python.exe scripts/source_link_audit.py
.\.venv\Scripts\python.exe scripts/final_live_e2e.py
```

Live E2E cần PostgreSQL cho phép tạo DB QA riêng, Edge và các cổng 8788/9338 khả dụng. Script dùng fixtures mô phỏng, xóa DB QA khi kết thúc và ghi `qa_final/results.json`/screenshots. Không dùng kết quả này để tuyên bố FaceID/GPS thực địa hay accuracy chatbot người dùng thật.
