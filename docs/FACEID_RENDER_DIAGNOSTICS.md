# Chẩn đoán FaceID trên Render

Không cần sửa database để kiểm tra model. Trong Render Shell của Web Service đang phục vụ website,
chạy lệnh chỉ đọc sau và lưu kết quả cùng runtime log của request bị lỗi:

```bash
python manage.py check_face_runtime
python manage.py check_face_runtime --load-engine
```

Command thứ hai khởi tạo model, chạy một tensor smoke không phải khuôn mặt để kiểm tra dtype/shape,
đo thời gian và RSS process; không ghi FaceAudit, FaceChallenge, FaceProfile, FaceEmbedding hay Attendance.
Xem Metrics/Logs của toàn instance để đánh giá RAM/CPU thực tế; số của process Shell không phải toàn service.
Nếu command chưa có trong bản đang chạy thì cần deploy bản đã review trước; đừng nhầm kết quả local với Render.

Đối chiếu `manifest_present`, mỗi asset `present/hash_matches`, packages, `engine.ready`, model_version,
`matching_profiles/mismatched_profiles`, embedding_dimensions (bộ hiện tại 128).
Giữ đúng SHA-256 FaceNet của profile hiện hữu; không dùng model khác rồi hạ threshold để ép nhận diện.

Trong Logs, tìm traceback tương ứng POST `/work/faceid/quality/` hoặc
`/management/ai/faces/quality/`. Phân biệt:

- FileNotFoundError/manifest/model thiếu: cung cấp asset đúng hash.
- ImportError/libGL/shared library/ONNX/MediaPipe: sửa dependency Linux theo traceback thực tế.
- InvalidArgument: đối chiếu dtype float32, tensor NHWC 160×160×3, model và input.
- Process killed/OOM hoặc gateway 502/504: đối chiếu Metrics và restart logs; không tự suy ra cold start.
- 401/redirect login: hết phiên; 403: quyền/CSRF; 400 JSON: chất lượng frame, challenge hoặc nhận diện bị từ chối.

Sau khi chủ hệ thống duyệt cung cấp model, có thể dùng lệnh cài asset sau **trong bước build đã duyệt**:

```bash
python manage.py download_ai_models --face-only
python manage.py check_face_runtime --load-engine
```

Lệnh download có network và ghi file model/manifest, không ghi database. Mặc định file ở
`ai_models/pretrained`; có `--assets-cache /duong-dan-da-duyet` cho storage riêng.
Đảm bảo file có trong runtime image; file tải ở Shell trên ephemeral filesystem có thể mất khi redeploy.
Không thêm download vào request camera hoặc start command. Giữ Build Command `bash build.sh`, Start Command
`daphne -b 0.0.0.0 -p $PORT restaurant_system.asgi:application`; nếu cài trong build thì phải review bổ sung
bước face-only vào build.sh. **Bản sửa local đã thêm bước này vào build.sh** sau khi Render Logs
xác nhận FileNotFoundError ở đường dẫn ổ D:. Chưa push/deploy hoặc thay Render configuration.

Trên iPhone: Safari HTTPS, cho phép Camera; ADMIN test không cần GPS để quyết định danh tính.
Trong Web Inspector/Network ghi từng request challenge → quality → verify, status, Content-Type,
thời gian, kích thước payload, 5/25 frame theo challenge. Không đưa ảnh/cookie/password vào log công khai.
Kiểm tra video nguồn dọc được giữ tỷ lệ; không kéo méo sang 640×480.
Trang chấm công phải có tài khoản liên kết nhân viên, profile tương thích, ca APPROVED và policy GPS hợp lệ.
Không tạo ca/chấm công mẫu trên production để thử; kiểm tra vào/ra ở staging/test database riêng.

## Bổ sung GPS trực tiếp và quyền cấu hình — 11/11/2026

Trang chấm công tự xin GPS trong chế độ cần vị trí, dùng watchPosition high accuracy, maximumAge=0; marker theo vị trí thiết bị, không thay tọa độ nhà hàng. Có thời gian cập nhật, nút vị trí của tôi/nhà hàng/hai điểm. Khi GPS lỗi/cũ/dừng, bỏ marker thiết bị thay vì dùng mặc định. Preview máy chủ lần đầu và kiểm tra chủ động không ghi lịch sử di chuyển; secure_punch vẫn xác minh độc lập.

Chỉ ADMIN có quyền change_restaurantinfo mới chỉnh cấu hình. GET không ghi; fieldset khóa đến khi bấm chỉnh sửa, cần checkbox xác nhận và dialog trước lưu. Editor RestaurantInfo chung cũng chặn MANAGER/STAFF để không vượt quyền qua đường khác. Không đổi policy mode, radius, accuracy hoặc threshold production trong tác vụ này. Test cấu hình dùng database test riêng và dữ liệu fixture.

Chrome headless: 5 trang kết hợp × 6 viewport 320–1440, 30 lượt, kiểm tra map bám GPS mô phỏng, chuyển góc nhìn nhà hàng/thiết bị, từ chối quyền, accuracy thấp/cũ và khóa punch. Không phải Safari/iPhone/Android phần cứng hay FaceNet người thật. Model, ngưỡng, GPS geofence và liveness không được thay đổi bởi gói bổ sung.

Một request tile OSM từ máy kiểm thử bị ConnectionError, không có HTTP status; browser cũng hiển thị fallback. Chưa thể kết luận 403/CSP hoặc lỗi Render. GET trang chủ Render 200 không có CSP, không thay thế kiểm tra trang quản lý đã xác thực. Thông báo tileerror hướng dẫn kiểm tra Network và giữ tọa độ hiển thị; không proxy/vượt chặn hoặc tự chuyển dịch vụ trả phí. Cần kiểm tra tile trên thiết bị/mạng thật sau triển khai được duyệt.

PR #2 đã được push để review; chưa merge/deploy. Bổ sung này thuộc yêu cầu mới sau gói 23 file ban đầu; manifest/patch đã duyệt trước đó được giữ làm bằng chứng phiên bản cũ. Booking/bàn thuộc PR #3, kiểm thử kết hợp trên worktree riêng; không gộp PR.

Kiểm thử chốt bổ sung trên cây kết hợp: **647/647 PASS, 455,408 giây**, Windows/Python 3.14 và PostgreSQL test riêng, parallel 2. Check/migration drift/collectstatic DEBUG=False PASS trên cây kết hợp và từng nhánh. Browser cuối 30/30, không JS exception hoặc local asset HTTP lỗi; GPS/camera/API mô phỏng, không nhận diện người thật trên Render. Không đổi binary/model_version hoặc chạy migration production. Linux build, Safari/iPhone/Android phần cứng và tải tile trên mạng thực vẫn cần xác minh sau phê duyệt.
