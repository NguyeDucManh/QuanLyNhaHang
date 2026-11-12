# Thiết kế phân công phục vụ bàn — chờ duyệt production

Migration dự kiến: `customers/0022_table_service_assignment.py`. Chưa áp dụng lên database local nghiệp vụ hoặc Render. Chỉ database test riêng đã chạy migration để kiểm thử.

`TableServiceAssignment` liên kết bàn với WorkSchedule đã duyệt, lưu khoảng bắt đầu/kết thúc, người giao, thời điểm tạo và thời điểm kết thúc phân công cũ. Nhân viên được suy ra từ lịch; không sao chép tài khoản hoặc sửa lịch. Các khóa ngoại dùng PROTECT. Database kiểm tra khoảng thời gian dương, có index theo bàn/thời gian và khóa duy nhất có điều kiện cho phân công chưa bị thu hồi.

Service kiểm tra ADMIN/MANAGER và quyền hiện hữu; nhân viên phải hoạt động, ca hoạt động và lịch APPROVED. Khoảng giao nằm trong ca, không giao hồi tố. Transaction khóa nhân viên → lịch → bàn; khóa bàn tuần tự hóa các thao tác phân công cạnh tranh. Kiểm thử hai kết nối đồng thời xác nhận chỉ một phân công trùng giờ được nhận. Ràng buộc giao nhau giữa các lịch được thực thi tại service; không thêm extension PostgreSQL.

Đổi người phải chọn thay thế rõ ràng. Bản ghi cũ được giữ và cắt hiệu lực tại thời điểm mới, có AuditLog người thao tác. Phân công cũ không tự tiếp tục sau khi khoảng mới kết thúc. Hủy lịch hoặc nhân viên ngừng hoạt động làm phân công không còn hiệu lực khi đọc.

STAFF không được tự cấp quyền xem tất cả bàn/booking. Khi bật chức năng, nhân viên thấy bàn được giao trong ca hiện tại; người thiếu quyền xem booking chỉ thấy thời gian, số khách và trạng thái, không thấy tên/ghi chú khách. Quyền quản trị bàn hiện có vẫn cho phép xem toàn bộ. Mở đơn từ booking kiểm tra phân công hiện tại đối với STAFF.

`TABLE_SERVICE_ASSIGNMENTS_ENABLED` mặc định false: không truy vấn bảng mới khi chưa migrate. Không bật cờ trước migration. Không tự tạo phân công, lịch hoặc nâng quyền để kích hoạt giao diện.

## Trình tự cần chủ hệ thống phê duyệt

1. Review mã, migration và SQL tại `artifacts/service-migration-review.log`; duyệt nhánh/PR riêng khi sẵn sàng. Gói FaceID PR #2 không được sửa trong tác vụ này.
2. Sao lưu database đích tại thời điểm triển khai, kiểm tra kế hoạch migration trên đúng phiên bản code. Migration chỉ tạo bảng/index/constraints, không có RunPython hoặc backfill.
3. Sau phê duyệt riêng mới chạy migration production, triển khai code và bật cờ môi trường. Không chạy seed hoặc tự giao bàn.
4. Quản lý kiểm tra nhân viên/lịch thật rồi tự tạo phân công đúng nghiệp vụ. Xác minh quyền và giao diện trên Render.
5. Nếu cần ngừng chức năng, tắt cờ; giữ bảng và nhật ký. Không tự reverse migration vì có thể mất các phân công đã tạo.
