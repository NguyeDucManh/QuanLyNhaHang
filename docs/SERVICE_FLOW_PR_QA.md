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

## Bổ sung chọn bàn và xem lịch theo giờ — 11/11/2026

Kết quả 621 tests ở trên thuộc commit 573b794 trước bổ sung này. Hiện có thêm lựa chọn bàn cụ thể, snapshot toàn bộ bàn theo ngày/giờ/sức chứa/khu vực và gợi ý thay thế không chứa danh tính. Lưu vẫn kiểm tra dưới khóa PostgreSQL; có test hai kết nối cùng chọn một bàn, khoảng giao nhau/liền kề/khác ngày và cọc còn/hết hạn. Order còn mở quá giờ booking chặn bàn cho tới khi được giải phóng, không tự đóng order hoặc sửa booking cũ.

Sơ đồ nhân viên nhận thời điểm xem lịch, chỉ hiển thị dữ liệu theo quyền. Xem thời điểm khác không cho thao tác mở đơn như hiện tại; trạng thái lịch sử là booking theo dữ liệu đang có, không tái dựng thời điểm Order đã kết thúc. Danh sách mở đơn cũng che tên khách khi thiếu view_booking. STAFF không được tự cấp quyền xem cả 20 bàn: người có quyền xem tất cả thấy toàn bộ; người chỉ được giao bàn thấy đúng phạm vi hiện tại.

Không có migration mới hoặc đổi migration 0022. Cờ phân công vẫn mặc định false. Dữ liệu production chỉ được SELECT qua TLS verify-full. 26 booking được phân loại thành 6 hủy, 10 lịch sử, 10 lượt tương lai hết hạn cọc; không có booking còn hiệu lực tại thời điểm kiểm kê, nên không tạo đơn/đặt giả để lấp sơ đồ.

Đã tạo cây kết hợp PR #2 + #3 để chạy regression; không merge hai nhánh. Focused booking 70 tests PASS; bộ cuối bổ sung privacy/concurrency/GPS gồm 23 tests PASS (10,859 giây). 30 lượt browser Chrome 320–1440 kiểm tra giao diện và GPS mô phỏng, không thiết bị thật. Một lượt full đầu lỗi 8 subtest static do worktree chưa collectstatic; đã chuẩn bị manifest DEBUG=False trước lượt full tiếp theo. Kết quả full kết hợp cuối được ghi trong PR khi hoàn tất; Linux/Render build vẫn chưa thực thi.

Kết quả chốt trên cây kết hợp cuối: **647/647 PASS, 455,408 giây**, Windows/Python 3.14, PostgreSQL test riêng, parallel 2. Check/drift và collectstatic DEBUG=False PASS. Cả hai nhánh riêng cũng check/drift/collectstatic PASS. Không cộng 23 test focused vào 647 để tạo số full giả; lượt 646 trước đó chưa có test privacy cuối. Browser chạy lại sau sửa lựa chọn bàn xung đột: 30/30, không tràn ngang/JS exception/asset HTTP lỗi. Không thay migration 0022 hoặc môi trường Render; cờ phân công mặc định false.
