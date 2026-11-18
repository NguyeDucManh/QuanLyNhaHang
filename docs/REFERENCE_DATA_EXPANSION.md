# Bổ sung dữ liệu vận hành (không đổi thực đơn)

Bản mở rộng này tạo **50 công thức tham khảo**, **5 nhà cung cấp DEMO** và tối đa **20 danh mục nguyên liệu**. Không chỉnh sửa `MenuItem`, `RecipeIngredient`, đơn giá bán, đơn hàng, booking, Stripe, tồn kho hoặc phiếu nhập/xuất. Các công thức tham khảo **không dùng để tự động trừ kho** và không được coi là công thức bếp đã duyệt.

## Chạy trên máy đang có Django

1. Sao lưu PostgreSQL trước khi thay đổi schema/dữ liệu.
2. Lấy nhánh `feat/reference-recipes-suppliers-seed` vào bản local sau khi xử lý những thay đổi đang làm việc.
3. `python manage.py migrate`
4. Xem trước: `python manage.py seed_reference_expansion`
5. Chỉ khi muốn ghi dữ liệu: `python manage.py seed_reference_expansion --apply`
6. Kiểm tra: `python manage.py test customers.test_reference_expansion`

Chạy lại bước 5 không tạo trùng, không ghi đè nội dung từng công thức hay trạng thái NCC đã chỉnh. Nếu mã mẫu bị trùng với bản ghi khác, chương trình dừng/rollback.

- Mã công thức: `DEMO-CT001` đến `DEMO-CT050`.
- Mã nhà cung cấp: `DEMO-NCC004` đến `DEMO-NCC008`. Không có người liên hệ, điện thoại, địa chỉ giả.
- Mã nguyên liệu mới: `DEMO-NL001` đến `DEMO-NL020`, bỏ qua tên đã tồn tại cùng đơn vị. Tồn đầu kỳ luôn 0, không tự nhập kho.
- Công thức minh họa có 4 nguyên liệu, định lượng cho mỗi phần, 5 bước chế biến, thời gian và cảnh báo cần bếp trưởng duyệt.

## Giới hạn

Hệ thống gốc chỉ có 35 món ăn, nên 50 công thức mới được lưu trong **RecipeReference độc lập**, không thêm món vào thực đơn. Không dùng các công thức tham khảo để tính giá vốn, lập phiếu hay vận hành bếp khi chưa được kiểm tra định lượng/yêu cầu an toàn thực phẩm.

Thay đổi mới chỉ nằm trên nhánh/PR, **không tự động ghi vào PostgreSQL local hoặc triển khai lên Render**.
