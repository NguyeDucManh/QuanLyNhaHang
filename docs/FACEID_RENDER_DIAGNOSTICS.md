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
