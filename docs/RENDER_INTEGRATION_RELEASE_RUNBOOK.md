# Tích hợp PR #2/#3/#4 và triển khai có phê duyệt

## Cây dependency được xác minh 12/11/2026

- main b170842; #2 open9d02c23→main; #3 open1f68568→main.
- integration/master-readiness3107bbd có cả hai nhánh bằng merge local, giữ nguyên commit nguồn.
- #4 fix/master-service-audit→integration/master-readiness, thêm scope/phiên bàn/CI. Không merge #4 vào base tích hợp rồi merge lại cả hai PR bằng cách thủ công copy file.

### Trình tự chính thức sau khi owner duyệt

1. Xác minh Auto-Deploy và branch Render trước merge. Nếu chưa biết, dừng thao tác main. Mọi thay đổi Auto-Deploy cần owner duyệt.
2. Review #2 và #3; sau phê duyệt mới merge lần lượt vào main. Lấy SHA mới, không giả SHA sau squash bằng commit nhánh gốc.
3. Trên worktree mới từ main vừa cập nhật, cherry-pick **chỉ các commit sửa riêng của #4** (commit sau base3107bbd), bỏ hai merge tích hợp. Dùng `git log --no-merges integration/master-readiness..origin/fix/master-service-audit` để chốt danh sách; review thứ tự từ cũ tới mới. Nếu cùng thay đổi đã có trong main, kiểm tra patch-id/diff, không ép copy đè hoặc cherry-pick lại.
4. Kiểm tra tree diff với cây ứng viên đã CI, giải quyết conflict theo final behavior, giữ root README/dữ liệu/private cache. Chạy checks/full regression trên SHA tích hợp mới; retarget/update #4 bằng nhánh đã review, không force-push không kiểm tra. Không coi CI của base3107bbd là CI của main mới.
5. Merge chính thức #4 chỉ sau owner duyệt. Không bật auto-merge. Không tạo PR release trùng toàn bộ #2/#3 để merge hai lần.

## CI Linux

`.github/workflows/ubuntu-regression.yml`: Ubuntu24.04,Python3.14.8,PostgreSQL17,Redis7 containers tạm, secret fixture không dùng production. Actions pin SHA; token contents:read, checkout không lưu credential. Không có bước deploy, production URL/credential hoặc seed production.

Pipeline: install requirements-production + pip check → schema0021/flagsOFF/public smoke → migrate0022/0023 → reverse/reapply trên DB CI rỗng → scheduler trên DB CI → pin FaceNet download/hash/engine128dim Linux → chạy đúng `bash build.sh` DEBUG=False → full regression gồm flagsON/OFF → hai Redis channel clients → operational readiness flagsON/Redis.

CI đã phát hiện lỗi native thật: MediaPipe1.1.0 không nạp được vì thiếu `libEGL.so.1` trên Ubuntu runner. CI cài libegl1/libgles2 cùng libgl1/libglib2.0-0/libportaudio2. `build.sh` nay chạy `scripts/check_face_native.py` để nạp thư viện native thật, không chỉ import Python; không truy cập database. Trên Render phải xem build log bước này. Nếu image thiếu thư viện hệ thống, build phải dừng; cần owner review phương án image có EGL/GLES (hoặc Docker) trước khi triển khai, không giả định apt/sudo được phép trên native Render và không bỏ qua guard.

Log CI ban đầu kéo cả NVIDIA/CUDA qua torch mặc định trên Linux. `scripts/install_production.sh` cài wheel CPU chính thức `torch==2.14.1+cpu` trước requirements (cùng phiên bản2.14.1), không đổi model hoặc threshold; CI kiểm tra version, không có CUDA và phép nhân tensor thật. Nguồn: [PyTorch CPU wheels](https://download.pytorch.org/whl/cpu/torch/). Build cũ có cache CUDA có thể còn package không dùng; không tự xóa cache production. Cần kiểm tra dung lượng build và RAM thực tế trên Render, không suy từ runner đủ RAM ra gói Free đủ RAM.

Job full dùng flags mặc địnhOFF; các test an toàn overrideON để kiểm tra assignment/sessions/object scope. Không chạy toàn bộ fixture legacy với globalON rồi nới assert để cho qua. Redis smoke dùng DB15 trên container tạm, không publish vào Redis production. Chạy từ PR và push main/integration, tránh nhân đôi job push/head của cùng PR.

## Cổng an toàn Render

Render có tích hợp khả dụng nhưng chưa connected trong phiên kiểm tra; local không có API credential Render. Do đó Auto-Deploy,branch,Build/Start Command,Metrics,Redis topology và external scheduler **UNKNOWN**, không suy từ `.env`, render.yaml hoặc trạng thái GitHub checks ra cấu hình đang chạy.

Render cho phép Auto-Deploy On Commit/After CI Checks Pass/Off; theo [tài liệu chính thức](https://render.com/docs/deploys), After CI Checks Pass có thể chấp nhận success/neutral/skipped, nên phải review job thực sự chạy, không coi skipped là regression PASS. Thay đổi setting là thao tác production cần duyệt.

### Trước triển khai

- Ghi serviceID/domain/branch,current deploymentSHA,Auto-Deploy mode,pending deployments từ Dashboard/API đã được cấp quyền. Không in environment values.
- Xác nhận PostgreSQL đúng đích; tạo backup cuối ở cửa sổ được duyệt, hash/TOC/decode và kiểm tra khả năng restore local. Backup đã có trong phiên master trước là bằng chứng rehearsal, không thay snapshot cuối.
- Check `python manage.py showmigrations customers` và `python manage.py migrate --plan` chỉ đọc trên đúng releaseSHA. Chỉ dự kiến0022→0023 CreateModel, không seed/backfill/RunPython. Nếu graph khác, review trước.
- Hai flags giữfalse trong lần deploy tương thích schema cũ. Build `bash build.sh`; Start `daphne -b 0.0.0.0 -p $PORT restaurant_system.asgi:application`. Không thêm migrate/seed/train vào build hoặc request startup.
- Đảm bảo RAM/CPU và shared libraries cho AI; CI Linux không chứng minh RAM gói Render. Không tải embedding RAG nặng chỉ để smoke public pages.

### Sau deploy code được duyệt, trước activation

1. Lưu deploymentID/logs/SHA trạng thái live thành công. Kiểm tra `/healthz/`, staticCSS/JS/SVG/map worker200 và đúngMIME; không kết luận chỉ từ build success.
2. `python manage.py check_operational_readiness`: SELECT-only schema/flags, hash vendor, expired-hold backlog, RedisPING nếu configured. `external_schedule_verified:false` luôn nhắc scheduler phải xác minh bên ngoài.
3. `python manage.py check_face_runtime --load-engine`: model hash/version,128dim,engine/RSS/time; không enrollment hoặc ghi Attendance. Command này có thể report engine.ready=false mà exit0; phải đọc JSON, CI wrapper đã assertready.
4. Chỉ sau phê duyệt migration mới áp dụng0022/0023. Không backfill TableSession vào booking/order lịch sử. Review legacy OCCUPIED/activeOrder riêng.
5. Chỉ sau phê duyệt activate hai flags và phân công thật theo ca đã duyệt; `check_operational_readiness --require-enabled`. Nếu nhiều process/instances, `--require-redis`; PING không thay kiểm tra delivery nhiều process trên Render.

### Scheduler cọc

Command hiện hữu `python manage.py expire_booking_deposits` mỗi phút: nó **ghi trạng thái booking/deposit**, cần owner duyệt scheduler. Không dùng `--stripe` nếu chưa duyệt thao tác provider. Không tạo Render Cron trả phí hoặc dùng web thread tự chạy job. Dùng scheduler đã được cấp quyền/chi phí phù hợp; kiểm tra last run/log/exit/backlog. Allocation bỏ cọc hết hạn bằng timestamp ngay khi đọc, nhưng không chứng minh external job đang chạy.

### Smoke test sau activation

- Public GET home/menu/login/robots/sitemap/health; canonical,HTTP,MIME. Không tạo session/challenge/order/payment để làm dữ liệu giả.
- ADMIN/STAFF A/B xác minh scope trên môi trường test được duyệt: detail/POST/partial/socket đơn bàn khác bị chặn; hủy lịch thu hồi socket.
- Test booking→deposit→arrival→assignment→order→kitchen→stock→invoice→payment→explicit release trên testDB/staging. Mocks Stripe/FaceNet không thay provider/device thật.
- iPhone/Android thật: GPS marker ưu tiên thiết bị, restaurant marker cố định150m/accuracy50m, không có ca/GPS không đạt thìkhóa; model thật/challenge/liveness không hạthreshold.
- OpenFreeMap: style/fonts/sprite/vector tiles và cùng-originworker200,CSP/WebGL không lỗi,attribution hiện; tile hỏng vẫn GPS. Không proxy/vượt chặn hoặc đổi APItrả phí.

## Rollback

Không reverse0022/0023 có dữ liệu, không DROP/TRUNCATE/restoređè production. Giữ backup,session,audit. Rollback code phải giữ tương thích schema và kiểm tra phiên mở/đơn chưa quyết toán. Tắt assignmentflag quay về quyền mô hình cũ, nên không coi đó là rollback bảo mật an toàn; owner duyệt cửa sổ hạn chế truy cập trước khi đổiflags/rollback. Ưu tiên roll-forward sau kiểm thử. Restore dữ liệu chỉ là phương án khôi phục sự cố riêng, cần owner duyệt phạm vi mất dữ liệu và quiescence, không tự động từ CI.

## Thao tác còn cần phê duyệt

Merge main chính thức; thay Auto-Deploy/Environment/Build/Start; deploy/redeploy; migrate production; bậtflags/giao ca/phân công dữ liệu thật; tạo Redis/Cron hoặc dịch vụ có phí; giao dịch Stripe/refund; retention/xóa dữ liệu. Kiểm thử/quản lý nhánh và CI tạm không cấp quyền làm các thao tác này.
