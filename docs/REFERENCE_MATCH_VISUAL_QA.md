# Đối chiếu UI với ba ảnh mẫu — lượt chỉnh bố cục

Quy ước giữ nguyên: **ảnh 1 Staff, ảnh 2 Admin/Manager, ảnh 3 Customer Web**.

Lượt này thay cấu trúc và tỷ lệ các khối, không chỉ đổi màu của bố cục cũ. Stylesheet nạp cuối là `static/ui/reference-match.css`; stylesheet `reference.css` vẫn giữ các chỉnh sửa trước đó.

## Đối chiếu trực quan

Ảnh mẫu được đối chiếu trực tiếp từ ba ảnh trong hội thoại. Không có bản gốc ba ảnh trong filesystem để chạy phép đo pixel/SSIM; báo cáo không khẳng định trùng từng pixel.

| Giao diện | Bố cục theo mẫu | Thay đổi so với lượt trước |
| --- | --- | --- |
| Staff | Tiêu đề, navigation xanh ngang; sơ đồ bàn bên trái; thông tin bàn bên phải; danh mục/menu dưới sơ đồ; đơn gần đây dưới panel bàn; bếp ở hàng cuối | Gom heading và bộ lọc bàn cùng hàng; nền sàn/cây trang trí; bàn dạng ô và tròn, có ghế; menu ảnh 3 cột; giảm khoảng cách để bếp xuất hiện trong màn hình desktop |
| Admin/Manager | Sidebar cream, topbar, hero ảnh nhà hàng, lời chào/ngày giờ/shortcut, 4 KPI, hàng chart–donut–booking, hàng top món–nguyên liệu–kho, hàng đơn–hoạt động | Bỏ các section nghiệp vụ xếp dọc; dùng lưới card liên tục với tỷ lệ cột khác nhau giữa các hàng; biểu đồ cột doanh thu và đường số đơn đều dùng dữ liệu thật |
| Customer | Navbar với menu giữa; hero chữ viết tay và ảnh món; form đặt bàn bên phải; thanh quick action; 4 món bên trái và ảnh không gian bên phải; hàng ưu đãi/combo/review; footer ngang | Bỏ các section dài xếp dọc ở trang chủ; đưa banner và review lên cùng hàng; nút thêm giỏ dạng dấu cộng, ảnh món crop đồng nhất |

Không tạo số liệu để lấp card. Các khối doanh thu hôm nay, booking sắp tới, top món đã thanh toán và tiêu thụ nguyên liệu có thể trống theo dữ liệu thực tế. Banner ưu đãi, combo, giá món và review đọc từ context ORM hiện có. Không thêm chương trình tích điểm/thành viên mới; dùng combo đang có cho card ưu đãi thứ hai.

## Ảnh kiểm tra thật

Thư mục `artifacts/reference-match-final/` chứa screenshot browser trực tiếp và `results.json`:

- `admin-1920.png` — 1920×1080; `admin-1366.png` — 1366×768.
- `customer-1920.png` — 1920×1080; `customer-1366.png` — 1366×768.
- `pos-admin-permissions-1920.png`, `pos-admin-permissions-1366.png` — **trang Staff/POS được mở bằng tài khoản hiện có đủ quyền**.
- `staff-1920.png`, `staff-1366.png` — tài khoản Staff thực tế, giữ nguyên thông báo nếu thiếu quyền xem bàn.
- Có thêm ảnh ở 1024, 768, 390px; Manager, FaceID và Assistant cũng được kiểm tra.
- `review.html` là trang xem các ảnh thật, đổi giao diện và kích thước bằng nút.

`artifacts/reference-match-round1/` và `reference-match-round2/` giữ hai lượt chụp trước khi sửa tiếp. Lượt 1 phát hiện CSS cũ chia đôi Admin và card món Staff bị ép chiều cao; lượt 2 đã sửa, sau đó tiếp tục gom spacing, chỉnh crop hero Customer và đưa bếp lên cao hơn.

## Kiểm tra chức năng

- `python manage.py check`: PASS.
- `python manage.py makemigrations --check`: không có thay đổi model.
- `python manage.py test --noinput`: **488 test PASS**, 280.942 giây. Log: `artifacts/reference-match-tests.log`.
- Browser đọc database vận hành, không seed/reset dữ liệu, không tạo order/booking/payment để làm đầy giao diện. Phiên đăng nhập QA được tạo tạm và xóa khi kết thúc; không đổi role hoặc permission.
- Không sửa business service, FaceID, thuật toán GPS, booking, thanh toán hay backend WebSocket. Chỉ bổ sung truy vấn trình bày cho chuỗi số đơn theo ngày, danh mục món, bếp và đơn gần đây.
- Hai mục AI vẫn là Quản lý khuôn mặt và Trợ lý nhà hàng.
- Không gửi chat hoặc thực hiện nhận diện/đăng ký khuôn mặt trong lượt QA này.
- Lượt browser cuối: **29 ảnh/trang-kích thước**, không có exception JavaScript hoặc tràn ngang toàn trang. Database có 20 bàn, mỗi bộ đếm trạng thái/khu vực khớp danh sách được lọc.
- Kiểm tra tương tác trong `artifacts/reference-match-interactions/results.json`: chọn B02 hiển thị đúng panel B02 và quay lại B01 thành công; tìm/lọc 45 món đúng; menu Customer và drawer Staff mở/đóng đúng ở 390px. Không tạo giao dịch.
- `artifacts/reference-match-review.patch` đối chiếu file text hiện tại với snapshot submission. Workspace không có metadata Git; patch này không phải Git diff và không bao gồm dữ liệu nhị phân ảnh.

## Asset trang trí

Tạo bằng công cụ **image_gen tích hợp**, không dùng CLI/API fallback:

- `static/ui/images/garden-restaurant-hero.png`: ảnh mood trang trí hero/banner/không gian; không phải ảnh xác nhận nhà hàng thực tế.
- `static/ui/images/botanical-floor.png`: nền sàn trống có cây ở mép. **Không chứa bàn, số bàn hoặc trạng thái**; tất cả bàn được render bằng HTML từ database.

Prompt hero: “Premium tropical garden restaurant at evening; warm pendant lamps, dark forest green velvet chairs, brass details, wood dining tables, crystal glasses, lush plants; plated steak in foreground right-center; dark green negative space on left; sharp editorial photography; champagne highlights; no people, text, logos, UI or watermark; decorative mood photograph.”

Prompt sàn: “Orthographic straight overhead restaurant floor background, landscape 4:3; warm beige wood planks, narrow cream walkways, tropical potted plants around outside edges, small warm garden lights; central 85% empty floor for real interactive HTML tables; no tables, chairs, people, text, numbers, labels or interface; light botanical architectural visualization.”

Ảnh món trong catalog hiện có được giữ nguyên. Không dùng ảnh AI làm món mới hoặc dữ liệu món giả.
