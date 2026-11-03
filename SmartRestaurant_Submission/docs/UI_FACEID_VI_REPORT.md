# Báo cáo UI nhận diện khuôn mặt, GPS và tiếng Việt

Cập nhật tiếp theo: [báo cáo staff portal](STAFF_PORTAL_REPORT.md). Trang chấm công STAFF đã dùng shell riêng; baseline 431 tests trong báo cáo này là snapshot lịch sử, regression mới đạt 445/445. Trạng thái chưa kiểm chứng camera/GPS và calibration thật giữ nguyên.

Ngày kiểm chứng: 14/10/2026, múi giờ Asia/Saigon. Phạm vi: lớp trình bày. Không thay FaceNet ONNX, cosine similarity, mean embedding/L2, 3–5 frame nhận diện, threshold mặc định 0,80 hoặc logic provisional/calibrated, 15-frame enrollment, identity, attendance service và Haversine. Không đổi dữ liệu đăng ký khuôn mặt hoặc dependency.

## 1. File sửa

- `customers/ui_labels.py`, `templatetags/ui_vi.py`: nhãn enum/thuộc tính, thông báo nội bộ và định dạng ngày giờ ở lớp hiển thị.
- `module07_forms.py`, `ai_forms.py`, `location_views.py`: chỉ labels/choice labels/thông báo uniqueness; giữ tên field, giá trị lựa chọn và validation.
- `static/ai/face-ui-vi.js`, `face-realtime.js`, `face-flow.js`: Việt hóa hiển thị, thời gian và hướng dẫn; GPS hiển thị ở test độc lập với geofence.
- `static/ai/face-guide.css`: oval lớn, vùng video riêng và HUD phía dưới; `templates/index.html`/attendance wrapper nạp stylesheet và trợ giúp ngôn ngữ.
- Templates FaceID/test/enrollment/employee link/attendance/location; HR lịch/chấm công/lương và các nhãn ở trang AI liên quan. Shared business table dịch tên field và trạng thái; JSON cấu hình, enum và attributes phục vụ JS giữ nguyên.
- Nhãn điều hướng ở `static/admin/js/main.js`, `static/ui/dashboard.js`; thông báo bản đồ ở `static/location/maps.js`.
- `customers/test_face_ui_vi.py`: 9 tests mới. `scripts/face_live_e2e.py`: kiểm chứng HUD, GPS permission, geometry và không tạo attendance ở test.

Không có migration mới; makemigrations --check báo không có thay đổi. Không sửa các service nhận diện/gợi ý/dự báo/booking/order/kitchen/payment/inventory/payroll.

## 2. Các nhãn đã Việt hóa

| Nhãn trước | Nhãn hiện tại |
|---|---|
| Employee code / Base salary | Mã nhân viên / Lương cơ bản |
| Enrollment / Samples / Last verify | Ngày đăng ký / Số mẫu / Lần xác thực gần nhất |
| Threshold / Threshold type | Ngưỡng nhận diện / Loại ngưỡng |
| Similarity / Cosine similarity | Độ tương đồng |
| Test recognition / Camera live | Kiểm tra nhận diện / Camera trực tiếp |
| CHECK-IN / CHECK-OUT | Chấm công vào ca / Chấm công ra ca |
| GPS accuracy / Lat / Lng | Độ chính xác GPS / Vĩ độ / Kinh độ |
| Payroll fields / HR statuses | Kỳ lương, phụ cấp, thưởng, khấu trừ, có mặt, đi muộn, về sớm… |
| Dashboard / Recommendation / Forecast | Tổng quan / Gợi ý món ăn / Dự báo |
| REAL / SYNTHETIC / PROXY | Dữ liệu thực tế / Dữ liệu mô phỏng / Chỉ số kiểm tra gián tiếp |

Thuộc tính kỹ thuật, enum backend, tên tài khoản/dữ liệu người dùng, thương hiệu và tên model được giữ. Không dịch biến/key JSON. Tên chỉ số cosine trong data-metric là metadata nội bộ, không phải text/tooltip hiển thị. Các lý do audit nội bộ có bản hiển thị tiếng Việt; số liệu và provenance không bị đổi.

## 3. Face guide trước/sau

Trước: desktop rộng 36%, cao 39%; mobile rộng 50%, cao 28%, guide ở phần trên và hướng dẫn chưa có vùng bố trí riêng. Sau: oval căn giữa vùng video, rõ hơn; dòng “Đặt khuôn mặt vào khung” ở dưới oval với nền mờ. HUD có vùng riêng phía dưới nên không che mắt/mũi/miệng. Video và vùng guide cùng chiều cao để căn mặt đúng.

Trạng thái/hướng dẫn: đặt mặt vào khung, đưa mặt vào giữa, tiến gần/lùi xa, giữ mặt thẳng, ảnh mờ, ánh sáng chưa đủ, phát hiện mặt, xác thực và kết quả. Các hướng dẫn chất lượng chỉ hỗ trợ UI, không thay tiêu chí server. Khi liveness=false không hiển thị yêu cầu blink/quay đầu; enrollment vẫn giữ hướng trước/trái/phải/trước như cũ.

## 4. Kích thước mới

| Viewport | Vùng video | Rộng oval | Cao oval |
|---|---|---|---|
| 1366×768 | Cao 600px | Khoảng 52%, tối đa 420px | 66%, tối đa 520px |
| 1920×1080 | Cao 600px | Khoảng 52%, tối đa 420px | 66%, tối đa 520px |
| 390×844 | Cao 500px | 74% | 60% |

Giới hạn layout 1280px giữ tỷ lệ desktop. Measurement bằng getBoundingClientRect trong browser, so vùng video dành cho khuôn mặt; không tính thêm phần thông tin HUD phía dưới. Có thể cuộn dọc trên mobile để xem toàn bộ thông tin/nút; không tràn ngang.

## 5. GPS HUD ở trang kiểm tra

`/management/ai/faces/test/`: giờ/camera, vị trí Vĩ độ/Kinh độ, độ chính xác GPS và kết quả nhân viên/độ tương đồng/ngưỡng/loại ngưỡng. Bật vị trí bằng nút rõ ràng hoặc khi bắt đầu nhận diện. watchPosition chỉ cập nhật browser, không gửi tọa độ lên server.

Không có reverse-geocoder hiện hữu nên dùng tọa độ; không bịa địa chỉ hoặc thêm API/secret. GPS ngoài vị trí nhà hàng hay bị từ chối permission không khóa nhận diện. Test không tạo Attendance/location event. Không thêm Leaflet/mini map vào trang này.

## 6. GPS HUD ở chấm công

Giữ vị trí/accuracy/radius, trạng thái phạm vi, nhân viên/score/ngưỡng/type và hai nút chấm công tiếng Việt. Khoảng cách realtime ghi rõ “ước tính trên giao diện”; khoảng cách hệ thống riêng được trả khi kiểm tra phạm vi hoặc chấm công. watchPosition không polling server hoặc lưu lịch sử di chuyển. Server vẫn validate tọa độ, tự tính Haversine và verify khuôn mặt theo policy hiện hữu; client flags không quyết định kết quả.

Giữ FACE_ONLY/GPS_ONLY/FACE_AND_GPS ở backend; UI trình bày “Chỉ nhận diện khuôn mặt”, “Chỉ xác thực vị trí”, “Khuôn mặt và vị trí”. Không mini map; bản đồ chỉ giữ ở cấu hình nhà hàng. Dừng/rời trang dừng camera và clearWatch.

## 7. Ngày giờ

Clock và kết quả dùng Intl.DateTimeFormat vi-VN, timeZone Asia/Ho_Chi_Minh. Templates HR/audit dùng ui_vi chuyển timezone rõ ràng, không phụ thuộc timezone thiết bị. Ví dụ timestamp UTC `2026-10-14T03:19:14Z` hiển thị giờ `10:19:14`, ngày `14/10/2026`; không in ISO thô trong kết quả người dùng.

## 8. Mapping trạng thái

| Backend | Người dùng thấy |
|---|---|
| PROVISIONAL | Ngưỡng tạm thời |
| CALIBRATED | Ngưỡng đã hiệu chỉnh |
| GPS_ALLOWED / ALLOWED | Trong phạm vi |
| GPS_DENIED / DENIED | Ngoài phạm vi |
| GPS_ACCURACY_LOW / ACCURACY_LOW | Độ chính xác GPS chưa đạt |
| GPS_UNAVAILABLE | Không lấy được vị trí |
| GPS_INVALID | Vị trí không hợp lệ |
| ACTIVE / INACTIVE | Đang hoạt động / Ngừng hoạt động |
| DRAFT / APPROVED / CANCELLED | Bản nháp / Đã duyệt / Đã hủy |
| PRESENT / LATE / EARLY_LEAVE | Có mặt / Đi muộn / Về sớm |

Mô tả: “Ngưỡng tạm thời — chưa hiệu chỉnh bằng dữ liệu kiểm định thực tế.” Không gọi ngưỡng tạm là đã hiệu chỉnh. Dữ liệu backend không được dịch/đổi giá trị.

## 9. Responsive/live browser

[Evidence](../evidence/ARCHIVE_NOTICE.md) và [server log](../evidence/ARCHIVE_NOTICE.md): Edge live HTTP, PostgreSQL QA riêng. 15 viewport checks trên các trang danh sách/test/enrollment/location/attendance, thêm ảnh FACE_AND_GPS; không tràn ngang. Measurement xác nhận tỷ lệ guide, caption/HUD ở dưới oval. GPS test hiển thị dù tọa độ mock nằm xa nhà hàng, không gửi check_location, không ghi location event. GPS_ONLY vào/ra ca vẫn dùng service thật; camera mock mở/dừng; GPS permission denied có thông báo tiếng Việt; timezone và JS parse PASS. Không có Runtime.exceptionThrown.

Ảnh: [kiểm tra với camera mock](../evidence/ARCHIVE_NOTICE.md), [test mobile](../evidence/ARCHIVE_NOTICE.md), [attendance mobile](../evidence/ARCHIVE_NOTICE.md), [desktop](../evidence/ARCHIVE_NOTICE.md).

Tiles OpenStreetMap ở trang cấu hình vẫn có lỗi mạng ERR_CONNECTION_REFUSED trong môi trường QA; URL lỗi được giữ trong evidence. Camera pages không phụ thuộc tiles. **Camera/GPS ở evidence là mô phỏng, không phải kiểm chứng sensor hoặc nhận diện người thật.**

## 10. Tests

9 tests mới kiểm tra labels, enum values giữ nguyên, thời gian UTC→Việt Nam, HUD test/attendance, không map/không nạp Leaflet ở trang camera, không blink khi tắt liveness, không Attendance khi GET test, hooks chất lượng enrollment và consent không bị hỏng. 37 tests UI + FaceID operational PASS. Giữ toàn bộ 422 tests baseline; **full regression 431/431 PASS**, test runner 355,225 giây. Check, makemigrations --check, migrate --noinput và pip check PASS: [verification results](../evidence/ARCHIVE_NOTICE.md)/[log](../evidence/ARCHIVE_NOTICE.md). Sau giới hạn nạp Leaflet, chạy lại riêng 9 tests UI cũng PASS.

Một test cũ kiểm tra metric identifier trong HTML được giữ tương thích bằng data-metric; không sửa test cũ và không đưa nhãn tiếng Anh trở lại UI. Source audit đọc 305 file, không có lỗi: [source_audit.json](../evidence/ARCHIVE_NOTICE.md). Không có migration/dependency/model weights mới; dữ liệu FaceProfile/embeddings chính không bị mutate bởi task UI này.
