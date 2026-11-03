# FaceID + nhân viên thật + GPS attendance realtime

Ngày: 14/10/2026 (Asia/Saigon). Scope chỉ FaceID/Employee identity/GPS attendance; giữ Django, PostgreSQL, FaceNet ONNX CPU, stack AI, các module nghiệp vụ và 394 tests baseline. Báo cáo này cập nhật trạng thái FaceID của [FINAL_REPORT.md](FINAL_REPORT.md); số liệu cũ là snapshot lịch sử.

Cập nhật UI mới hơn: [UI_FACEID_VI_REPORT.md](UI_FACEID_VI_REPORT.md). Nhãn enum kỹ thuật bên dưới vẫn giữ trong code/log; người dùng hiện thấy bản tiếng Việt, oval lớn và GPS hiển thị độc lập ở trang kiểm tra nhận diện. Các logic trong báo cáo này tiếp tục được giữ.

## 1. Vì sao UI trước đây hiện DEMO

`seed_module07_operational_data` tạo Employee cho User MANAGER/STAFF chưa có profile, dùng mã `DEMO-U{user.pk:04}` và tên `Nhân viên DEMO…`. Nó đã dùng chính tài khoản hiện hữu, không chỉ tài khoản mới `demo_m07_*`. FaceID list cũ lấy tất cả Employee nên các nhãn seed xuất hiện trên UI vận hành.

Audit readonly trước chỉnh sửa: [employee_accounts_audit.json](../evidence/ARCHIVE_NOTICE.md). Có 7 User active, 5 Employee và 0 operational Employee theo marker. Không ghép tên hoặc đoán danh tính.

## 2. Phân biệt real/seed

`employee_identity.operational_employees()` tập trung rule: loại mã `DEMO-` không phân biệt hoa/thường và tài khoản `demo_m07_*`; yêu cầu Employee/User active, employment_status ACTIVE và vai trò nhân viên. `require_operational` kiểm tra lại target phía server. Không hard-code rule trong template. Không thêm field nguồn vì seed có prefix xác định rõ; migration chỉ bổ sung loại threshold cho audit.

Một tài khoản thật đã liên kết với Employee mang nhãn seed vẫn cần quản lý xác nhận mã/họ tên thực trước khi dùng vận hành. Xác nhận dựa User ID/OneToOne hiện có; không tự suy diễn mã nhân viên hoặc thay tên hàng loạt.

## 3. Dữ liệu DEMO có bị xóa không

Không xóa, không relink User, không tạo Employee trùng. 5 hồ sơ seed và mọi references vẫn giữ. Audit trước: mỗi Employee có 7 WorkSchedule và 1 Payroll; Attendance tương ứng 4/3/3/3/3. Employee #3/User #4 có 1 FaceProfile và 15 FaceEmbedding từ trước task này. Không suy ra các mẫu này đã có consent hoặc được kiểm chứng webcam thật chỉ từ sự hiện diện trong DB.

Màn hình xác nhận chỉ đổi thuộc tính Employee khi manager chủ động POST form hợp lệ; giữ nguyên PK/User/FaceProfile/references. Không tự chạy cleanup hoặc xác nhận trên DB chính.

Kiểm tra sau task: User 7, Employee 5, WorkSchedule 35, Attendance 16, Payroll 5, FaceProfile 1, FaceEmbedding 15; không thay các số bản ghi này trong DB chính.

## 4. Tài khoản thực và Employee

| User | Role | Employee hiện hữu | Hành động cần thiết |
|---|---|---|---|
| Manh0508 | ADMIN | Chưa có | Tạo Employee nếu cần self attendance |
| KimAnh — Vũ Thị Kim Anh | STAFF | #1, nhãn seed | Xác nhận mã/họ tên thật |
| QuocHuy — Lê Quốc Huy | MANAGER | #2, nhãn seed | Xác nhận mã/họ tên thật |
| MinhHoang — Nguyễn Minh Hoàng | STAFF | #3, nhãn seed; 15 mẫu FaceID | Xác nhận hồ sơ và đúng người/consent của mẫu |
| AnhToan — Phạm Nguyên Anh Toàn | STAFF | #4, nhãn seed | Xác nhận mã/họ tên thật |
| VanQuyet — Trương Văn Quyết | STAFF | #5, nhãn seed | Xác nhận mã/họ tên thật |
| CongDat — Lê Công Đạt | CUSTOMER | Chưa có | Không thuộc FaceID vận hành |

Như vậy không có STAFF/MANAGER thiếu OneToOne; vấn đề là nhãn seed. Chỉ ADMIN chưa có Employee. [Audit hiện tại](../evidence/ARCHIVE_NOTICE.md) gồm group/direct permissions, references và số mẫu; command không lấy mật khẩu/.env/embedding vectors.

## 5. FaceID operational list

`/management/ai/faces/` dùng helper operational, có họ tên/username/mã/chức vụ/active/FaceID/samples/enrollment/threshold/type/last verification/actions. Nhật ký vận hành cũng loại Employee seed. Quản lý vẫn có phần “Tài khoản cần xác nhận hồ sơ nhân viên” hiển thị tài khoản thật và link an toàn, không trình bày nhãn DEMO như nhân viên vận hành.

Hiện DB chính chưa được tự xác nhận nên operational table trống và hiển thị hướng dẫn. Đây là trạng thái có chủ đích để người có thẩm quyền xác nhận mã/consent. Sau xác nhận, hồ sơ xuất hiện và mẫu đã có vẫn gắn cùng Employee ID. Screenshot QA dùng fixtures tách biệt, không phải danh sách thật đã được cập nhật tự động.

## 6. Enrollment mapping

Admin/Manager có change_employee → target route resolve operational Employee từ DB → active/role validation → 15-frame UI enrollment hiện hữu → FaceProfile/FaceEmbedding. Body employee_id không được dùng thay target route. UI và HTTP yêu cầu consent=true; không lấy embedding do client cung cấp. Re-enroll thay samples, reset threshold/calibration; delete POST/CSRF và confirmation giữ Employee/HR history.

Màn hình `/management/ai/faces/accounts/<user_id>/` tái sử dụng EmployeeForm/save_resource hiện hữu, khóa User field, xác nhận rõ ràng, kiểm tra unique và lock User. Tạo mới cần add_employee; sửa cần change_employee; không đổi role/quyền theo chức vụ.

## 7. Straight-face recognition

Mặc định: camera → kiểm tra đúng một mặt/size/blur/brightness/pose gần thẳng → 5 frame cách nhau khoảng 240 ms → preprocessing/FaceNet ONNX → mean embedding/L2 → cosine → threshold. Server nhận 3–5 frame khi liveness false, từ chối frame lặp và abs(yaw)>0,15. UI không yêu cầu blink/head turn. Thời gian camera thu mẫu khoảng 1,2 giây; tổng request có thêm CPU/model/network, không cam kết luôn dưới 2 giây.

Test page chỉ verify và ghi FaceAudit, không ghi Attendance. Self test resolve Employee qua request.user; không tin employee_id/verified. Khi chấm công, server verify lại với challenge mới; pass trên HUD không thay thế backend verification.

## 8. Metric

Giữ cosine similarity cho FaceNet embedding L2; enrollment template là mean/L2 của samples. Recognition độc lập dùng mean/L2 các frame; liveness-enabled path giữ kiểm tra identity theo từng frame/min cosine hiện hữu và margin 0,05 giữa hai profile. Không đổi sang distance metric khác. Giá trị similarity là kết quả request, không phải biometric accuracy.

## 9. FACEID_DEFAULT_THRESHOLD

Default server `0.80`, override qua biến `FACEID_DEFAULT_THRESHOLD`. Đây là điểm bắt đầu local bảo thủ trong metric cosine hiện có và phù hợp mức threshold đã dùng trong kiểm thử trước; **không có validation thực địa chứng minh đây là threshold tối ưu**. Giá trị phải finite trong (-1,1]. Không hard-code threshold trong JS/template.

```dotenv
FACEID_DEFAULT_THRESHOLD=0.80
FACEID_REQUIRE_LIVENESS=false
```

Chưa tự sửa .env hoặc bất kỳ calibration/profile threshold hiện hữu nào.

## 10. Provisional / calibrated

Profile.threshold khác null → ưu tiên threshold profile, type CALIBRATED. Null → dùng default, type PROVISIONAL. UI ghi “Ngưỡng tạm thời — chưa hiệu chỉnh bằng dữ liệu validation thật.” Audit lưu effective threshold/type. Loại threshold phản ánh cấu hình DB, không chứng minh chất lượng calibration; calibration command/metadata/datasets vẫn giữ nguyên. Không tạo FAR/FRR/EER/accuracy giả.

Helper nghiên cứu/legacy giữ strict defaults để baseline test calibration-rejection không bị sửa. Các HTTP vận hành và secure attendance truyền policy explicit cho provisional/liveness theo settings; không dùng strict legacy helper làm endpoint bypass GPS.

## 11. Liveness config

`FACEID_REQUIRE_LIVENESS=false` mặc định: challenge một lần action straight và 3–5 frame; không thực thi basic challenge. `true`: challenge blink/left/right ngẫu nhiên, neutral → action → neutral, 8–30 frame. Challenge phải thuộc actor, đúng mode server, chưa dùng và chưa hết 90 giây; quality/liveness fail vẫn tiêu thụ challenge. Đây là bảo vệ cơ bản, không phải anti-spoof chuyên dụng. Liveness=false không được ghi audit như liveness pass.

## 12. GPS realtime HUD

Camera lớn/oval guide, CAMERA LIVE chỉ khi stream hoạt động, giờ Asia/Ho_Chi_Minh, tọa độ/accuracy/radius/status và FaceID name/score/threshold/type. Check-in/out lớn, disabled khi thiếu ca, cấu hình, GPS mới/đạt hoặc face preview mới/đạt. Dừng/rời trang dừng tracks và clearWatch; không mini map attendance. Floating assistant được ẩn riêng ở trang này để không che HUD mobile.

`watchPosition` chỉ cập nhật browser, không gửi hoặc lưu mỗi update. Khoảng cách realtime từ tọa độ mới được ghi rõ **ước tính UI**; “Khoảng cách server” riêng lấy từ nút kiểm tra phạm vi rõ ràng hoặc attendance attempt. Điều này tránh polling location lên server mà vẫn phân biệt tính toán quyết định phía server với preview. Tọa độ stale hơn 20 giây hoặc face preview hơn 30 giây làm nút chưa sẵn sàng; server vẫn xác minh mọi attempt.

## 13. Reverse geocoding

Không có reverse-geocoder phù hợp trong stack hiện hữu nên dùng fallback Lat/Lng; không gửi vị trí nhân viên đến API bên thứ ba, không thêm secret hoặc bịa địa chỉ. Không resolve tên đường không ảnh hưởng chấm công. Địa chỉ nhà hàng trong settings không được giả làm địa chỉ hiện tại của nhân viên.

## 14. Server Haversine

Giữ Haversine R=6.371.008,8 m. Server validate finite/bounds/accuracy, load config DB và so radius/maxaccuracy. Client inside/distance/gps_allowed/verified không được tin. Internal statuses ALLOWED/DENIED/ACCURACY_LOW giữ tương thích; API có status_code GPS_ALLOWED/GPS_DENIED/GPS_ACCURACY_LOW, lỗi GPS_UNAVAILABLE/GPS_INVALID. GPS browser vẫn là tọa độ client khai báo, có thể bị spoof; server tính khoảng cách không chứng minh sensor thật.

## 15. Attendance policy/service

Giữ FACE_ONLY/GPS_ONLY/FACE_AND_GPS, default policy FACE_AND_GPS. FACE_ONLY không thu GPS; GPS_ONLY không bật camera. Secure service resolve operational Employee theo actor, chỉ nhận ca thuộc chính Employee, thực thi required components rồi gọi personnel.punch hiện hữu. Thành công ghi Attendance + location event + FaceAudit trong transaction; fail không mutate Attendance. GPS missing/invalid và face failure có event/audit tương ứng. Preview check_location không ghi movement history. Ca/duplicate/in-out/kỳ lương tiếp tục được kiểm tra trong service cũ.

## 16. Privacy

Không tạo fake enrollment; không ảnh AI, raw video, raw face photo lưu bền; embeddings server-side không trả UI/log. Frame JPEG chỉ ở RAM request/browser và bỏ sau xử lý. Enrollment có consent confirmation; dữ liệu đã có cần manager xác nhận đúng người/consent trước dùng. Không tracking location liên tục phía server. Audit chỉ score/threshold/type/reason/timestamp và event attempt. Delete/re-enroll giữ HR và tài khoản.

## 17. Files sửa

Identity: `employee_identity.py`, `employee_identity_views.py`, readonly command `audit_employee_accounts.py`, template employee_link/operational_faces. Face: policy.py, face_enrollment_service.py, liveness_service.py, facenet_service.py; ai_phase_views/final_views. Attendance: location_service/location_views, routes, settings. UI: face-realtime.js/css, wrapper templates/straight_test/realtime_attendance, face-flow.js chỉ giữ enrollment, consent và navigation chấm công. QA: test_face_operational.py, face_live_e2e.py, template refresh scripts và compatibility selectors cho E2E cũ. Không đổi recommendation/forecast/chatbot/booking/order/kitchen/payment/inventory/payroll services.

## 18. Models/migration

Thêm `FaceAudit.threshold_type` blank/default empty cho lịch sử chưa ghi nhận; migration `0018_faceaudit_threshold_type.py`. Không sửa User/Employee OneToOne, không tự migrate nhãn seed sang real, không cập nhật embeddings/FaceProfile threshold. Check/makemigrations/migrate PASS.

## 19. Tests thêm

28 tests mới: operational filter/read-only audit/confirmation giữ ID/unique/consent/RBAC/enrollment mapping, provisional/calibrated/mean metric/poor quality/pose/duplicates/no enrollment/embeddings, test-only không Attendance, challenge owner/mode/replay, liveness-enabled rejection, spoof employee_id, ba policy modes, geofence/boundary/NaN/inf/accuracy/missingGPS/audit/no mutations, sai identity và ca không thuộc actor. Biometric inputs trong tests được mock, không tính là dữ liệu thật.

## 20. Regression

Baseline 394 tests giữ nguyên. **Full regression cuối 422/422 PASS** (394+28), test runner 473,646 giây; check, makemigrations --check, migrate --noinput và pip check đều PASS. Xem [verification results](../evidence/ARCHIVE_NOTICE.md) và [log](../evidence/ARCHIVE_NOTICE.md). Không sửa/xóa test cũ để đạt PASS. Source/template/URL/static audit đọc 299 file nguồn, không có lỗi: [source_audit.json](../evidence/ARCHIVE_NOTICE.md).

## 21. Live browser

[QA evidence](../evidence/ARCHIVE_NOTICE.md): live Django/PostgreSQL/Edge trên DB QA UUID tách biệt, xóa cuối lượt. Manager routes FaceID/test/enrollment/location 200; role STAFF/CUSTOMER quản lý FaceID 403; GPS giả/missing denied; GPS_ONLY check-in/out UI gọi service thật; watch HUD không ghi DB; camera mock start/stop; 15 viewport checks ở 1366×768/1920×1080/390×844, thêm FACE_AND_GPS screenshots. Không Runtime.exceptionThrown. OpenStreetMap tiles trên settings bị ERR_CONNECTION_REFUSED do truy cập mạng; evidence giữ URL lỗi, local Leaflet/static và HUD không phụ thuộc tiles.

Ảnh: [attendance mobile](../evidence/ARCHIVE_NOTICE.md), [attendance desktop](../evidence/ARCHIVE_NOTICE.md), [test camera mock](../evidence/ARCHIVE_NOTICE.md), [operational list QA](../evidence/ARCHIVE_NOTICE.md). Screenshot dùng fixture QA, không chứng minh đã xác nhận hồ sơ chính. Không tạo FaceProfile/embedding QA trong live script; camera mock màu test không dùng làm enrollment hay xác nhận nhận diện thành công.

## 22. Thao tác thủ công còn cần

1. Manager vào FaceID → tài khoản cần xác nhận → nhập mã/họ tên thật và xác nhận; không đổi liên kết User. Với Manh0508 tạo Employee chỉ khi cần attendance. Kiểm tra consent và đúng chủ mẫu MinhHoang trước dùng; nếu chưa rõ, re-enroll đúng người.
2. Enrollment giữ 15 mẫu trước/trái/phải/trước, đồng ý consent, lưu. Test nhìn thẳng với liveness=false và nhãn PROVISIONAL.
3. Cấu hình vị trí/radius/accuracy/mode thật và ca đã duyệt. Đăng nhập staff → Nhân sự → Chấm công → bật GPS/camera → FaceID → check-in/out. Server verify lại; không chỉ dựa HUD pass.
4. Kiểm tra webcam/permission/ánh sáng thật; GPS sensor/accuracy/geofence thật; cả ba mode, outside/low accuracy/duplicate/in-out. Chạy calibration command với genuine/impostor validation/test riêng; không dùng ảnh enrollment làm test.

**Chưa có evidence phần cứng thật hoặc biometric accuracy/calibration thật từ task này.** 1 profile/15 mẫu hiện hữu được bảo toàn, không tự tuyên bố là enrollment đã được xác minh thực địa. Không tuyên bố FaceID/GPS đạt 100%.
