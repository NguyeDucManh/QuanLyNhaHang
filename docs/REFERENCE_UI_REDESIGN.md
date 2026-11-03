# Redesign theo ba ảnh mẫu

Quy ước: mẫu 1 là Staff, mẫu 2 là Admin/Manager, mẫu 3 là Customer Web.

**Lượt chỉnh bố cục bám sát ảnh mẫu mới nhất:** xem [REFERENCE_MATCH_VISUAL_QA.md](REFERENCE_MATCH_VISUAL_QA.md). Stylesheet nạp cuối hiện là `static/ui/reference-match.css`; ảnh mới trong `artifacts/reference-match-final/`.

## Thay đổi

- Dùng chung bảng màu cream, forest green, champagne gold; stylesheet cuối cùng là `static/ui/reference.css`.
- Staff ưu tiên POS: sơ đồ bàn, bộ lọc khu vực/trạng thái, thông tin bàn, menu và đơn đang phục vụ. Phần ca làm, chấm công và thu nhập giữ ở mục mở rộng.
- Sơ đồ lấy `RestaurantTable`, `Area`, booking hiện tại và order đang hoạt động qua truy vấn chỉ đọc trong `customers/pos_presentation.py`. Mỗi ô giữ primary key thật; không sinh thêm bàn.
- Trạng thái và bộ đếm dùng chung danh sách. Khi lọc khu vực, bộ đếm được tính lại từ các bàn thuộc khu vực đó.
- Chọn bàn và làm mới dữ liệu không tải lại toàn trang. Dùng kênh WebSocket bếp hiện có khi đủ quyền, cùng cập nhật nền mỗi 30 giây.
- Admin/Manager có sidebar sáng, hero, bốn KPI, biểu đồ doanh thu, booking sắp tới, top món, top nguyên liệu, cảnh báo kho, đơn và hoạt động gần đây.
- Menu AI chỉ hiển thị Quản lý khuôn mặt và Trợ lý nhà hàng. Không xóa model, service hoặc test AI cũ.
- Customer giữ cấu trúc website: navbar, hero, đặt bàn nhanh, menu, gợi ý hiện có, combo, ưu đãi, đánh giá, thông tin nhà hàng và footer. Dữ liệu đặt bàn nhanh chỉ điền trước form hiện có; xác thực và xếp bàn vẫn qua luồng cũ.
- Báo cáo giới hạn biểu đồ ở top 5, dữ liệu đầy đủ trong mục mở rộng. Bảng thanh toán gọn hơn; mã dài rút gọn ở danh sách, giữ mã đầy đủ tại tooltip và chi tiết.
- Bản đồ bỏ lớp tile khi tải lỗi, giữ tọa độ, marker và bán kính. Có fallback khi hết thời gian chờ; không thay thuật toán GPS/chấm công.

## Phân quyền và dữ liệu

Không reset hoặc seed database vận hành. Không thay business service, migration, FaceNet, embedding, threshold, booking, payment hoặc WebSocket backend.

Staff không có quyền xem bàn sẽ thấy thông báo thiếu quyền. Không tự cấp thêm quyền để hiển thị dữ liệu. Tài khoản Staff được kiểm tra trong database hiện tại chưa có quyền xem bàn; POS đầy đủ được đối chiếu bằng tài khoản có quyền.

## Kiểm tra

- `python manage.py check`: PASS.
- `python manage.py makemigrations --check`: không có thay đổi model.
- `python manage.py test --noinput`: 488 test PASS. Không sửa/xóa test cũ; thêm bốn kiểm tra về tính đúng của sơ đồ và phân quyền.
- Browser: Admin, Manager, Staff, Customer và POS tại 1920, 1366, 1024, 768, 390px; FaceID và Assistant tại desktop/mobile. Không có exception JavaScript hoặc tràn ngang toàn trang trong kết quả lưu.
- Database có 20 bàn; POS hiển thị 20 bàn và bộ đếm trống 20. Bộ lọc khu vực có bốn khu, mỗi khu 5 bàn; mọi kiểm tra bộ đếm đều khớp.
- Ảnh và kết quả: `artifacts/reference-qa/`; fallback vị trí: `artifacts/reference-qa-extra/`; lượt kiểm tra cuối của hóa đơn và báo cáo: `artifacts/reference-qa-financial/`.

Workspace không có metadata Git. `artifacts/reference-ui-review.patch` đối chiếu với bản snapshot `SmartRestaurant_Submission`, không phải Git history. Không sửa bản submission hoặc tạo lại ZIP trong task này.

Browser QA chỉ kiểm tra giao diện FaceID/Assistant; không đăng ký khuôn mặt, không gọi nhận diện thật, không gửi tin nhắn hoặc tạo giao dịch vận hành.
