# Luồng đặt bàn customer và thanh toán

Ngày kiểm chứng: 15/10/2026, Asia/Saigon. Tiếp tục Django/PostgreSQL hiện hữu. Phạm vi là bố cục, bản nháp session và điều hướng; không thay model, migration, dependency hoặc service nghiệp vụ.

## 1. Booking UI trước/sau

Trước: form tạo, tóm tắt và danh sách lịch sử cùng một màn hình; liên kết thực đơn nhỏ và thiếu hành động quay lại. Sau: hai workspace độc lập, CTA chọn món rõ ràng, màn hình xác nhận riêng và trạng thái thanh toán có giải thích.

## 2. Đặt bàn mới / Đặt bàn của tôi

`/booking/?view=new` chỉ có form, món đã chọn và tóm tắt bản nháp. `/booking/?view=mine` chỉ có danh sách, các nhóm sắp tới/hoàn thành/hủy/lịch sử và bộ lọc. Lịch sử bao gồm toàn bộ đặt bàn của chủ tài khoản, phân trang 15 dòng. Các link `?tab=...` cũ vẫn mở workspace danh sách. Lần truy cập đầu mặc định tạo mới; URL cũ không có query trong session vừa đặt thành công có thể mở lại xác nhận gần nhất để giữ tương thích. Chọn tab Đặt bàn mới luôn mở form độc lập.

## 3. Booking draft lưu ở đâu

Session Django phía server, key `customer_booking_draft`, có owner và whitelist các trường có giới hạn độ dài. POST có CSRF, `intent=menu` lưu cả form chưa đầy đủ rồi chuyển thực đơn. Không chạy validation tạo booking ở bước này; không giữ bàn hoặc tạo Booking/Order. GET trả form không ghi DB nghiệp vụ. Nếu không có draft, dùng tên tài khoản hoặc thông tin liên hệ gần nhất của chính khách làm giá trị mặc định. Response booking có `Cache-Control: no-store`.

## 4. Menu booking mode

Chỉ opt-in khi URL có `from=booking` và người dùng đăng nhập. Query filter/category, liên kết chi tiết món, thực đơn và combo giữ ngữ cảnh. URL thực đơn thường không tự bật mode từ session. Chọn topping/số lượng dùng endpoint giỏ hiện hữu; combo dùng endpoint combo hiện hữu với đích quay về được whitelist.

## 5. Sticky CTA

Thanh cố định có số phần, tổng tiền từ server, nhãn chưa thanh toán, Xem món đã chọn và Đã chọn món xong. Sau AJAX thêm món, count/total cập nhật từ preview server. Done là GET về `?view=new`, không checkout hoặc ghi Booking. Ẩn floating assistant riêng trong mode này để không che thanh CTA. Không cần JavaScript để lưu draft hoặc bấm Done.

## 6. Selected foods restore

Form initial lấy draft đúng owner. Giỏ không được sao chép thành dữ liệu frontend: preview đọc cart/topping_cart/combo_cart hiện hữu, lấy giá/availability từ DB. Hiển thị ảnh/tên/số lượng/giá món/thành tiền, topping và thành phần/số lượng/giá combo; tổng ghi rõ tạm tính chưa thanh toán. Có chỉnh sửa món, tăng/giảm/xóa và xóa combo. Lỗi cart vẫn hiển thị, không tự coi dữ liệu lỗi là hợp lệ.

## 7. BookingItem attach

Chỉ POST xác nhận hợp lệ gọi `create_booking` hiện hữu. Service tiếp tục auto-assign, kiểm tra capacity/overlap và tạo snapshot trong transaction, bao gồm topping/combo. Callback commit xóa draft và cả ba giỏ chỉ sau thành công; form/service lỗi giữ draft và giỏ. Redirect GET xác nhận và reload không attach lại. Service booking không có request-key idempotency tổng quát; task giữ hành vi đó, không tuyên bố chống mọi POST lặp đồng thời. Không tạo OrderItem ở bước đặt bàn.

## 8. Payment lifecycle hiện tại

Booking → BookingItem snapshot → nhân viên mở Order → kitchen/order hoàn tất → `issue_invoice` → yêu cầu Payment → khách báo thanh toán → nhân viên xác nhận. Các service, quy tắc transition, snapshot và pricing giữ nguyên. QA thanh toán chỉ là fixture nội bộ, không phải giao dịch ngân hàng. Không thêm deposit/prepaid.

## 9. Khi nào nút Thanh toán xuất hiện

Read-only helper kiểm tra order.customer là request.user, order COMPLETED, invoice UNPAID và không có payment PENDING/SUCCEEDED. Khi đó hiển thị Thanh toán ngay tới trang invoice hiện hữu. Pending có link theo dõi; invoice PAID có nhãn Đã thanh toán và link hóa đơn. Các endpoint order/invoice/payment vẫn kiểm tra owner ở server. ID confirmation khác chủ hoặc không hợp lệ trả 404.

## 10. Vì sao booking mới chưa thanh toán được

Booking vừa tạo chưa có Order hoàn tất/Invoice. Confirmation và mỗi card danh sách luôn có khu vực Thanh toán, lời giải thích và nút Chưa thể thanh toán bị disabled. Không mở đơn/xuất hóa đơn để làm nút hoạt động. UI dịch trạng thái payment; persisted enum không đổi.

## 11. Files sửa

`customers/customer_booking_workspace.py` mới; `views.py`, `booking_workspace.py`, `module07_views.py` tích hợp composition và điều hướng. Templates booking, draft summary, confirmation, payment, menu bar/combo, menu/filter/dish/detail, header/footer, shared booking panel/extras và combo page. `static/ui/customer-booking.css`, `booking-workspace.js`, `static/customer/js/main.js`. `customers/test_customer_booking_workspace.py` và `scripts/customer_booking_live_e2e.py` cho kiểm chứng. Không sửa test cũ hoặc các booking/cart/order/kitchen/invoice/payment services.

## 12. Tests thêm

21 tests: workspace riêng, default/deep-link/history owner, draft partial/restore/owner/CSRF, normal/booking menu, detail/filter context, giữ quantity/topping/combo, optional preorder, snapshot một lượt/reload, clear sau commit/giữ khi lỗi, confirmation/invalid ID/owner, payment unavailable/payable/pending/paid, quyền invoice/payment và mobile hooks.

## 13. Tổng tests PASS

**482/482 PASS**, gồm 461 tests cũ giữ nguyên và 21 tests mới; test runner 532,005 giây. 24 tests trọng tâm cũng PASS sau các sửa lỗi tương thích. Django check, makemigrations --check, migrate --noinput và pip check PASS. Xem [verification](../evidence/test_summary.json), [full test log](../evidence/ARCHIVE_NOTICE.md) và [source audit](../evidence/ARCHIVE_NOTICE.md). Không sửa/xóa test cũ để đạt PASS; không thay dependency.

Bản source sạch đã được kiểm chứng riêng: check/migrate/seed/routes, FaceNet/MediaPipe CPU, embedding CPU, FAISS và artifact forecast/recommendation PASS; [evidence](../evidence/clean_verification.json). DB smoke test đã xóa. Dùng interpreter đã chuẩn bị, không tuyên bố đã cài mới dependencies trên máy khác. Gói cập nhật loại .env/.venv/model cache và giữ manifest portable; checksum/kích thước ghi tại `submission_audit/customer_booking_after.json` và `SmartRestaurant_Submission.zip.sha256`.

## 14. Browser E2E

**PASS.** Evidence: [JSON](../evidence/customer_booking_browser_summary.json), [server log](../evidence/ARCHIVE_NOTICE.md). Edge live HTTP/PostgreSQL UUID riêng: nhập draft → bấm menu → chọn 2 phần món có topping + combo 2 phần → Done → kiểm tra từng field/giỏ → xác nhận → confirmation → mine. Tạo 3 dòng snapshot đúng cách phân bổ combo hiện hữu; không tạo Order trong bước booking. Tiếp tục lifecycle thật bằng service trong QA để kiểm tra chưa thể thanh toán/payable/pending/paid. Không có Runtime exception, HTTP error hoặc network failure trong lượt cuối. DB QA đã được xóa; không seed hoặc xác nhận giao dịch trên DB chính. Các bước tương tác customer dùng browser DOM; phần kitchen/invoice/payment chuyển trạng thái bằng service trong script QA, không tuyên bố đã click toàn bộ UI của nhân viên.

## 15. Mobile result

**36/36 kiểm tra viewport không tràn ngang.** Các trạng thái draft/menu/restored/confirmation/mine/payment và normal menu được đo ở 1920×1080, 1366×768, 768×1024, 390×844. Ảnh: [draft mobile](../evidence/booking-draft-mobile.png), [menu mobile](../evidence/booking-menu-mobile.png), [khôi phục](../evidence/booking-restored-mobile.png), [xác nhận](../evidence/booking-confirmation-mobile.png), [thanh toán](../evidence/booking-payment-mobile.png). Đây là Edge headless tự động, chưa đại diện mọi thiết bị/trình duyệt; không có kiểm chứng webcam/GPS thật trong task UX này.
