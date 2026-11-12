# Hotfix release MediaPipe trên Render — 12/11/2026

## Phạm vi và nguyên nhân

Main `d075d85c8c80daae5b27048642c852a28ff8bc14` là squash merge PR #6,
cây mã khớp release `527e1c6`; đã có PR #2–#5. Không merge/cherry-pick lại các PR đang mở.
FACE_ONLY được giữ, GPS/Map tiếp tục bị loại khỏi runtime, dữ liệu vị trí lịch sử không bị xóa.
Không đổi Booking/area/table/assignments/membership/FaceID threshold/liveness hoặc model_version.

Traceback Render cho thấy MediaPipe không dlopen được `libGLESv2.so.2` khi build kiểm tra native.
Đây là thư viện hệ điều hành (Debian package `libgles2`), không được cung cấp chỉ bằng pip.
CI cũ cài apt packages trên runner/image riêng; PASS đó không chứng minh Render Python native có cùng thư viện.
Không gỡ check và không bắt exception rồi tiếp tục build.

## Giải pháp được chuẩn bị

Dockerfile production dựa trên Python3.14.8/Debian12 bookworm, cài libgles2/libegl1/libgl1,
libglib2.0-0/libportaudio2/libgomp1 ngay trong image. Build vẫn gọi `bash build.sh`,
kiểm tra native MediaPipe/ONNX CPU, tải/hash model FaceNet/landmarker, check Django và collectstatic.
Không có migrate/seed trong build hoặc entrypoint. Build dùng cấu hình giả chỉ trong RUN,
không yêu cầu/kết nối PostgreSQL production hoặc bake DATABASE_URL/secret vào image.
Runtime dùng user không phải root, entrypoint kiểm tra native rồi exec Daphne với `$PORT`.

Dockerfile.ci512 kế thừa **chính image production**, không có apt/pip riêng để che lỗi.
CI kiểm tra startup bằng CMD production, health với PostgreSQL CI, redirect HTTP/HTTPS proxy và MIME static.
Cgroup512MiB/không swap/1CPU chạy real model, quality, tensor và ảnh mẫu detector/embedding5/25,
chat fallback/public/admin/staff và concurrency. Ảnh mẫu public-domain NASA do scikit-image phân phối,
URL và SHA256 pin trong driver CI; không đóng gói ảnh vào image, không dùng nhân viên production.
5/25 lần xử lý cùng ảnh không phải kiểm định liveness/danh tính hoặc FAR/FRR.

Negative check trên base Debian/Python không cài thư viện phải tái hiện thiếu SONAME;
positive check phải thực sự tải MediaPipe native và ONNX CPU. CI chưa hoàn thành thì không ghi PASS.
Kết quả final SHA, logs, RAM và mọi lỗi được công bố ở Draft hotfix PR Checks/body và báo cáo local.

Requirements Python giữ nguyên pin đã tích hợp: MediaPipe1.1.0,ONNXRuntime1.31.0,Python3.14.8,
CPU Torch/XGBoost theo install_production.sh. Thư viện OS được quản lý ở Dockerfile.
Không dùng Dockerfile.ci512 hoặc scripts.render512_settings làm cấu hình production.

## Render: thao tác cần duyệt, chưa thực hiện

Theo [native runtimes](https://render.com/docs/native-runtimes), Render native dùng Debian12;
[Docker](https://render.com/docs/docker) là phương thức có hỗ trợ để kiểm soát OS packages ngoài runtime có sẵn.
Có thể [đổi runtime của service hiện hữu](https://render.com/docs/native-runtimes#changing-a-services-runtime),
không cần tạo lại Web Service/domain/PostgreSQL. Docker chỉ thay cách đóng gói, không thay gói RAM trả phí.

**Chưa xác minh qua Dashboard:** Auto-Deploy OFF, runtime/running SHA, RAM cấp thực tế,
service DATABASE_URL/Redis/scheduler và secret files. Không suy ra từ CI hoặc báo cáo cũ.
Không có quyền Render API/CLI/Shell đang dùng được trong phiên kiểm tra.

Sau khi CI đạt, phải xác minh các gate sau trước khi xin duyệt cuối:

1. Service đúng `smart-restaurant-demo.onrender.com`, Git repo/branch main đúng, Auto-Deploy **OFF** thực tế.
2. Backup PostgreSQL còn hợp lệ; tạo backup sát cutover nếu đã có dữ liệu phát sinh; review pending migrations.
3. Giữ nguyên DATABASE_URL/credential/Stripe/domain, DEBUG=false và ba feature flag OFF;
   không in môi trường/secrets. Kiểm tra `.dockerignore` với mọi secret file được cấu hình trên Render.
4. Không có pre-deploy command tự migrate/seed/flush. Nếu đang có, thay đổi cần được duyệt riêng.
5. Review runtime change sang Docker và kế hoạch rollback; chưa bấm Save/Deploy trước phê duyệt.

### Một đợt deploy thống nhất sau phê duyệt cuối

- Khi Auto-Deploy OFF đã xác minh, merge **chỉ hotfix PR** vào main một lần, ghi lại SHA mới.
- Trong service hiện hữu, Settings → Build → Source → Edit, giữ repo/branch main,
  chọn runtime Docker, Dockerfile Path `Dockerfile`, build context repository root.
- Native Build Command `bash build.sh` được thay bởi Docker build (Dockerfile vẫn chạy script đó).
  Để Docker Command trống để dùng CMD `bash scripts/start_render.sh`; CMD exec Daphne
  `-b 0.0.0.0 -p $PORT restaurant_system.asgi:application`.
- Giữ toàn bộ env production cần thiết; không đặt DJANGO_SETTINGS_MODULE sang module CI.
  Giữ Assignments/Lifecycle/Membership OFF, không tự bật trong rollout.
- **Đổi runtime qua Dashboard có thể khởi động deploy ngay**; gộp toàn bộ cấu hình vào cửa sổ đã duyệt,
  không Manual Deploy bản Python thiếu libs trước đó, không bấm deploy thêm lần thứ hai.
  Auto-Deploy OFF chỉ kiểm soát Git-trigger, không được coi là chặn mọi deploy do thay config.
- Không chạy migration tự động. Nếu được phê duyệt trong cùng cửa sổ, chạy đúng0022–0024 còn thiếu,
  timeout lock giới hạn, hậu kiểm counts/FK/hash/quyền; không reverse/drop/restore đè production.
  Code/flagsOFF đã tương thích schema0021 nên deployment không phụ thuộc tự migrate khi start.

## Kiểm chứng sau deploy, chưa được báo PASS trước khi có bằng chứng

Đối chiếu SHA commit của deployment trong Render, image/build/start logs và Web Service hiện hữu.
Kiểm tra native libs/MediaPipe/ONNX/manifest/modelhash,health/static200+MIME,home/menu/robots/sitemap,
GPS routes404/menu không GPS,booking chọn khu vực/bàn,membership rõ trạng thái ưu đãiOFF.
Không dùng số đo CI thay RAM/latency/OOM Render; theo dõi Metrics và request5xx trên deployment thật.
Đăng nhập/FaceChallenge/FaceAudit/Attendance và mọi business-write QA cần phiên được duyệt;
không tạo đơn/thanh toán/chấm công giả. Camera iPhone và danh tính/liveness nhân viên thật còn chưa kiểm chứng.

Migration0022–0024 không đổi trong hotfix, không migration mới. Backup/restore rehearsal và migration
trên bản sao Render đã PASS ở release trước; hotfix không lặp nhập dữ liệu hoặc reset PostgreSQL.
14 cọc hết hạn trước đó không được tự xử lý; cron/catch-up/provider writes vẫn cần phê duyệt riêng.

Rollback giữ dữ liệu và schema: dừng rollout/tắt tính năng mới theo phê duyệt, chọn artifact hoạt động đã xác minh,
không giả định d075d85 có thể rebuild trên Python native đang thiếu libs. Không rollback bằng DROP/reverse migration
hoặc restore đè dữ liệu phát sinh. Không nâng gói/tạo service mới nếu chưa được duyệt.
