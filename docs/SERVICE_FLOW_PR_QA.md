# Kiểm thử gói booking và phân công bàn

Nhánh độc lập từ main b170842; không chứa FaceID/GPS PR #2 hoặc các thay đổi khác trong workspace. Gói này tái sử dụng quản lý lịch và chấm công hiện hữu; không sửa threshold, GPS hoặc engine FaceNet. Chức năng phân công mặc định tắt.

Migration 0022 chỉ CreateModel: FK bàn/lịch/người giao dùng PROTECT tại ORM, FK database, check end > start, index khoảng bàn và unique có điều kiện. Không backfill, sửa bảng nghiệp vụ hoặc thêm quyền tự động. Chống giao nhau dùng transaction khóa bàn tại service và được kiểm tra cạnh tranh hai kết nối. Ghi trực tiếp SQL bỏ qua service không có exclusion constraint chống giao nhau.

Rollback trước commit của transaction phân công hủy cả bản ghi mới, thay đổi hiệu lực cũ và AuditLog. Sau khi đã dùng chức năng, rollback triển khai bằng tắt cờ và giữ bảng/dữ liệu; reverse migration sẽ DROP bảng phân công nên không được chạy tự động. Sao lưu không tự động cho phép xóa dữ liệu để phục hồi.

## Trình tự triển khai cần phê duyệt riêng

1. Sao lưu PostgreSQL đích ngay trước triển khai, xác minh archive và lập kế hoạch phục hồi.
2. Kiểm tra migration graph, SQL và migrate --plan trên đúng commit; đối chiếu migration 0022 chưa được dùng cho thay đổi khác.
3. Deploy code tương thích với TABLE_SERVICE_ASSIGNMENTS_ENABLED=false. Khi tắt, không truy vấn bảng phân công mới; kiểm tra các trang booking/bàn vẫn chạy.
4. Chỉ sau phê duyệt chạy migration production. Không seed, backfill, tự tạo ca hoặc phân công.
5. Sau kiểm tra schema, phê duyệt bật cờ và để quản lý tạo phân công thật từ lịch đã duyệt.
6. Kiểm tra trên Render: quyền, lịch, timeline, trạng thái cọc, bàn và nhật ký. Thử nghiệm ghi dùng môi trường test được duyệt; không tạo khách/đơn/thanh toán giả trên production.

PR #2 hiện còn mở. Bản vá FaceID/GPS áp dụng kiểm tra lên cây gói này không có conflict văn bản; hai gói cùng sửa urls.py nhưng khác hunk. Không sửa PR #2, không tuyên bố đã kiểm thử tích hợp hai gói nếu chưa chạy suite trên cây kết hợp. Cần kiểm tra lại khi main hoặc PR #2 thay đổi.

Kiểm tra giao diện trước tách: Edge headless, 5 trang × 6 kích thước 320–1440, 30/30; không tràn ngang, JS exception hoặc asset HTTP lỗi. Snapshot từ DB test, không phải browser E2E production hoặc iPhone thật. Lần kiểm thử trước trên toàn workspace đạt 672 tests; số test của nhánh sạch được ghi riêng sau khi chạy, không dùng số này thay thế.

Không push dữ liệu PostgreSQL, .env, AI cache, model binary hoặc artifacts chứa dữ liệu thật. Chưa merge, deploy, migrate hoặc thay đổi database Render.

## Kết quả trên nhánh sạch

- Windows, Python 3.14, PostgreSQL test local riêng: **621/621 PASS, 201,926 giây**, parallel 2. Bộ này không chứa test chưa công bố của FaceID/GPS và các tác vụ khác trong workspace; vì vậy không dùng số 672 của workspace làm kết quả nhánh.
- Django check: 0 issues. makemigrations --check --dry-run: No changes detected.
- collectstatic DEBUG=False: 233 file nguồn, 929 bước post-process, PASS. sqlmigrate 0022: PASS, chỉ xuất SQL, không áp dụng lên database nghiệp vụ.
- git diff --check và kiểm tra staged secret theo giá trị môi trường: PASS; chỉ 29 file nghiệp vụ/tài liệu. Cờ phân công mặc định false. Không thêm workflow hoặc thay đổi cấu hình Render.
- Trong lượt test trước khi collectstatic hoàn tất có warning thiếu thư mục staticfiles; collectstatic sau đó thành công. Warning runpy settings cũng xuất hiện trong test cấu hình, không có failure/error.
- Chưa chạy build Linux/Render thực tế hoặc full suite trên cây kết hợp PR #2. Kiểm tra áp dụng patch PR #2 chỉ xác nhận không xung đột văn bản.
