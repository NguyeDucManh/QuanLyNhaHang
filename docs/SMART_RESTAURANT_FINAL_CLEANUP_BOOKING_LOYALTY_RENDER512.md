# Smart Restaurant — kiểm toán cuối, FACE_ONLY, booking, thành viên và Render 512 MB

Ngày 12/11/2026. **Chưa nghiệm thu production; chưa xác nhận chạy ổn trong 512 MB.**
Mọi thay đổi nằm trong worktree riêng `artifacts/final-cleanup-worktree`, không trộn workspace gốc.
Không merge/deploy/migrate production, không thay environment hoặc dữ liệu PostgreSQL nghiệp vụ.
Yêu cầu mới FACE_ONLY thay thế yêu cầu GPS cũ; không thay threshold/liveness/model_version.

## 1. Kiểm kê module — PASS kiểm kê, không đồng nghĩa toàn bộ đã E2E

Kiểm kê AST 197 module Python, 190 template; danh mục class/function/test trong
`artifacts/FINAL_MODULE_INVENTORY.json` (local ignored). Các nhóm đã đối chiếu:

| Nhóm | Thành phần chính | Kiểm chứng |
| --- | --- | --- |
| Tài khoản/RBAC | auth, groups, capabilities, scope, Channels | regression PostgreSQL |
| Danh mục | category/menu/combo/topping/area/table | regression + HTTP fixture |
| Booking/cọc | capacity, overlap, holds, Stripe webhook, waitlist | regression; provider mock/ký fixture |
| Phục vụ | assignment, TableSession, POS, booking arrival/order | regression luồng liên phân hệ |
| Bếp/kho | kitchen transitions, recipes, stock, suppliers | regression, tồn kho chỉ trừ một lần |
| Hóa đơn | invoice, payments, applied deposit, member/voucher/refunds | regression tiền tệ/idempotency |
| Nhân sự | employees, shifts, approved schedules, attendance, payroll | regression; Face inference mock ở integration |
| Khách hàng | own bookings/orders/invoices, membership, chat | regression + browser fixture |
| AI | FaceNet, MediaPipe, chatbot grounded/RAG, recommendations, forecast, GA | Face tensor thật local; phần khác regression có giới hạn |
| Triển khai | WhiteNoise/build/native libraries/deposit scheduler/Redis | local checks/static; CI mới chưa chạy |

## 2. Chức năng giữ — PASS mã nguồn/test tương ứng

Giữ Stripe cọc thật qua server, thanh toán tiền mặt/chuyển khoản có xác nhận, tồn kho,
phân công/phiên bàn, booking và kiểm soát đồng thời, ca đã duyệt, FaceNet/liveness,
chat có phân quyền, GA, dữ liệu lịch sử và toàn bộ migration cũ. Không tạo dữ liệu demo production.

## 3. Lỗi đã sửa — PASS kiểm thử tương ứng

- FACE_ONLY kiểm tra nhân viên, ca thuộc tài khoản/APPROVED/khung giờ, danh tính và punch; không GPS.
- API chấm công cũ dùng cùng luồng bảo vệ; JSON có lỗi rõ, 429 khi engine đang bận.
- Đồng bộ subtotal/discount/total cùng lần lưu: sửa CHECK constraint lỗi khi order từ booking nhận ưu đãi.
- Bàn thuộc khu vực inactive không còn xuất hiện trong lựa chọn khách; backend vẫn kiểm tra capacity/overlap.
- Voucher không được chọn không tiêu hao; chuyển sang ưu đãi tốt hơn/huỷ đơn hoàn lại lượt có khóa.
- Tính lại số tiền giảm khi subtotal đổi nhưng giữ snapshot tier/rate/revision lúc chốt đơn.
- Refund đã đối soát được trừ khi xét hạng và báo cáo net, kể cả flag OFF sau rollback.
- Tổng chi tiêu tổng hợp PostgreSQL một query cho nhiều hóa đơn; menu RBAC lấy role một lần/request.
- Gợi ý live không import sklearn/pandas/torch hoặc dùng dataset nghiên cứu; forecast synthetic không hiển thị như thực.
- Enrollment bỏ nhánh GPS cũ, chụp theo tỷ lệ video thật và báo lỗi API không phải JSON.

## 4. Chức năng loại bỏ — PASS audit tham chiếu active

Gỡ GIS/GPS khỏi runtime chấm công, QR ngân hàng demo, trang gợi ý admin demo,
dashboard AI nghiên cứu cũ, placeholder JS/CSS/template không có người dùng, identity admin hardcode.
Giữ model/migration vị trí để bảo toàn lịch sử; không DROP bảng. Tài liệu lịch sử/archive không được xem là runtime.

## 5. File/route gỡ — PASS local, chưa deploy

Gỡ `customers/location_views.py`, `location_service.py`, `payment_demo.py`,
`static/location/maps.js`, vendor Leaflet/MapLibre, `templates/shared/map_assets.html`,
location settings/GIS demo, các forecast template trống và customer placeholder JS/CSS.
Route cũ `/management/settings/location/`, `/work/location/check/`, recommendation demo ADMIN,
QR demo không còn phục vụ. Regression xác nhận 404/phân quyền; không dùng redirect sang thao tác ghi.
Danh sách chính xác mọi file thêm/sửa/xóa: `artifacts/FINAL_UPGRADE_REVIEW_MANIFEST.json`.

## 6. Dashboard theo vai trò — PASS local, BLOCKED thiết bị thật/Render mới

ADMIN/MANAGER dùng thống kê và route nghiệp vụ thật, không identity giả hoặc kết quả nghiên cứu giả.
Quản lý chính sách thành viên/ghi hoàn tiền yêu cầu capability riêng; MANAGER không tự nhận quyền mới.
STAFF thấy công việc/bàn/ca theo quyền; CUSTOMER thấy booking, hóa đơn và thành viên của mình.
Danh sách khách quản lý bao gồm khách 0 điểm/chưa có CustomerLoyalty; có search/filter/pagination.

## 7. Khu vực/bàn ADMIN → CUSTOMER — PASS test DB

Tên khu vực lấy từ Area, không seed hoặc gắn cứng Tầng trệt/Lầu/VIP.
Test tạo/đổi tên/vô hiệu hóa khu vực và bàn qua HTTP quản trị, khách thấy trạng thái mới.
Kế thừa booking chống trùng/sức chứa/bảo trì/khung giờ và view Hôm nay/Sắp tới/Lịch sử.
Không chuyển booking lịch sử thành Order hoặc đánh dấu đang phục vụ giả.

## 8. Chính sách thành viên — PASS test, flag mặc định OFF

MEMBER <2.000.000đ:0%; SILVER ≥2.000.000đ:3%; GOLD ≥5.000.000đ:5%;
VIP ≥15.000.000đ:5% + quyền lợi cấu hình. Điểm thưởng là ledger riêng, không phải doanh số.
Chỉ tính Invoice PAID/Order COMPLETED có bằng chứng thanh toán/cọc áp dụng hợp lệ, trừ refund đối soát.
Mọi ngưỡng/rate được validate, cập nhật có audit và revision; không tự backfill thay lịch sử.

## 9. Giảm giá và voucher — PASS test

Decimal/ROUND_HALF_UP, không vượt subtotal; không cộng dồn, chọn ưu đãi hợp lệ cao nhất.
Snapshot tier/rate/spend/revision/benefits gắn Order, không sửa invoice cũ khi khách lên hạng.
Voucher tốt hơn được tính một lần; voucher thua không tiêu hao; retry và huỷ có kiểm tra/audit.

## 10. Đối soát cọc/hóa đơn/thanh toán — PASS test, chưa provider production

Cọc SUCCEEDED áp dụng tối đa invoice total, phần dư không biến thành doanh thu/điểm.
Cọc một phần: Payment chỉ cho balance; cọc đủ: không tạo Payment trùng.
Webhook ký fixture lặp không nhân đôi cọc/điểm. Payment retry giữ hợp đồng từ chối đã xử lý.
InvoiceRefund chỉ ghi khoản **đã hoàn bên ngoài** với reference duy nhất, giới hạn tổng đã thu,
không gọi Stripe/bank, không sửa invoice/ledger lịch sử. Không thử thanh toán/refund production.

## 11. Kiểm thử — cập nhật bằng chứng cuối ở phụ lục

- 27/27 test query/nghiệp vụ PASS,30,219s; 24/24 FaceID/tiền/static PASS,11,552s.
- 8/8 contract test PASS,1,648s (có warning cố ý override DATABASES để chứng minh CI fixture từ chối DB sai).
- Camera JS:11/11 PASS; API/camera mô phỏng, 5/25 frame, lỗi HTTP, malformed response, không GPS.
- Browser:56/56 PASS, tám trang × bảy width320/375/390/412/768/1024/1440,0JS errors/0asset errors/no overflow.
  HTML render từ PostgreSQL test riêng, không phải browser production hoặc Safari/iPhone thật.
- Lượt full trước lỗi8 static subcase do chưa collectstatic trong worktree mới; đã build static để chạy lại.
  Không bỏ test hoặc nới assertion nghiệp vụ. Test GPS/QR được đổi hợp đồng theo yêu cầu loại bỏ mới.
- Chưa chạy CI mới: không dùng kết quả664 test của PR4 cũ làm bằng chứng cho gói này.

## 12. Peak RAM 512 MB — BLOCKED thực thi Linux

Không có WSL/Docker local; push mới bị auto-review chặn nên chưa chạy workflow cgroup.
Đã chuẩn bị Docker/Ubuntu CI ép512MiB, swap=0,1CPU,1Daphne; PostgreSQL/driver ngoài cgroup.
Probe có pha public/booking/admin/staff/chat, native Face quality và25tensor128,30request/3concurrent,
lưu memory.max/current/peak/events và diagnostics cả khi thất bại. Fixture chỉ cho DB restaurant_ci512 localhost.
**Không có số peak512 hợp lệ để báo PASS.** Tensor không có mặt người không chứng minh nhận diện danh tính.

Local Windows trước/sau Face load:309,45→308,84MiB RSS;5,985→4,487s; tensor128:0,339→0,214s.
Đây là một lần đo, không benchmark thống kê và không đại diện cho Linux/toàn ứng dụng.
Hash hai model đúng, model_version1c69044b… giữ nguyên; số đo đầy đủ `FINAL_FACE_LOCAL_MEMORY.json`.

## 13. Khả năng vượt RAM — BLOCKED định lượng mới

PR4 cũ có Linux peak596.672KiB (~583MiB), chưa cgroup512; bằng chứng đó không đạt512.
Gói mới lazy-load ML, CPU-only Torch/XGBoost, ONNX tắt arena/mem-pattern, thread1,
serialize inference và malloc_trim Linux; chưa đo hiệu quả Linux nên không cam kết hết OOM.
Semantic RAG cần embedding/index thật và có thể vượt ngân sách khi cùng FaceNet;
fallback chỉ trả chính sách có nguồn code, unknown trả thiếu dữ liệu, không giả semantic readiness.
Không tự nâng gói trả phí hoặc tách dịch vụ production.

## 14. Git/PR — PASS cô lập nhánh, BLOCKED xuất bản mới

Nhánh `feature/face-only-loyalty-render512`, base PR4 `10d756058549d28a6180596bbff089728acb5477`.
GitHub kiểm tra lại12/11: main `b170842ce9ba0d58bbffb9517e7ade0a054ab284`;
PR2 `9d02c233…`/PR3 `1f685682…` open base main; PR4 draft open base integration/master-readiness.
Không có PR mới cho gói này. Tích hợp theo ancestry PR2+PR3→integration→PR4→gói mới;
không merge lại/squash chồng từng nhánh vào main làm mất thay đổi.
Auto-review từ chối publish vì phạm vi mới vượt gói23 file cũ; cần chủ hệ thống xác nhận lại phạm vi xuất bản.
Không tìm cách upload patch qua kênh khác để vượt từ chối.

## 15. Migration — PASS review, BLOCKED production approval

Graph0022(assignments)→0023(TableSession)→0024(thành viên).
0024 chỉ CreateModel MembershipPolicy/MembershipDiscount/InvoiceRefund, không RunPython/DELETE/UPDATE.
FK PROTECT, OneToOne Order, reference unique, amount constraints, singleton policy.
Chỉ áp dụng trong PostgreSQL test. SQL/plan và drift phải review trên commit cuối.
Rollback production: tắt feature mới, giữ bảng/dữ liệu mới và snapshot, rollback code tương thích.
**Không reverse0024 sau khi có dữ liệu**: reverse sẽ DROP ba bảng. Backup không tự cấp quyền xóa/ghi đè.

## 16. Rủi ro — BLOCKED nghiệm thu thực tế

Chưa browser camera phần cứng/Safari/iPhone, FAR/FRR, actual5/25frame real face Render, native512/OOM.
Chưa xác minh Render settings/AutoDeploy hiện tại, Redis topology/scheduler hoặc logs mới qua Dashboard.
Chưa đo latency/cold-start trước-sau production vì chưa deploy. Không suy ra hệ thống đã nhanh từ test local.
Refund ledger mới cần quy trình đối soát và cấp capability rõ; không tự cấp quyền cho tài khoản thật.

## 17. Bị chặn — BLOCKED

Push/PR/CI mới: automatic approval review; không có Linux cgroup local thay thế.
Dashboard/Shell/Metrics Render chưa được kết nối; không giả định Auto-Deploy On/Off theo báo cáo cũ.
Thiết bị thật/nhận diện danh tính cần phiên kiểm thử được đồng ý; không tạo chấm công giả.

## 18. Triển khai/rollback/smoke — BLOCKED production, kế hoạch đã chuẩn bị

1. Review patch/manifest/commit riêng; cho phép publish phạm vi mới; CI Ubuntu +512 phải chạy trên SHA cuối.
2. Xác minh Render branch/main, AutoDeploy, build `bash build.sh`, start Daphne đúng,512/native libs.
   Nếu AutoDeploy OnCommit, phải chốt cửa sổ triển khai và phê duyệt cấu hình trước merge; chưa tự chỉnh.
3. Backup PostgreSQL mới ngay trước triển khai, SHA/pg_restore archive và restore rehearsal ở môi trường riêng được duyệt.
   Backup/rehearsal cũ không thay backup tại thời điểm cutover.
4. Review SQL0022/23/24, schema drift/locks/counts, mọi feature flag OFF.
5. Sau phê duyệt merge/deploy: deploy code tương thích flagsOFF, xác minh SHA/build/modelhash/static/health.
6. Chỉ sau phê duyệt migration: áp dụng đúng migration còn thiếu, không seed/flush, so sánh dữ liệu/FK.
7. Sau phê duyệt bật flag: lần lượt assignments/lifecycle/membership; xác minh readiness/schema/Redis/scheduler.
8. Smoke public/login/menu/booking/member/admin/staff, MIMEstatic200, auth/RBAC, Face quality/verify bằng model thật.
   Việc ghi booking/order/payment/attendance dùng staging/test riêng; production cần phê duyệt riêng.
9. Theo dõi memory/CPU/error/latency; nếu lỗi tắt flag mới và rollback artifact tương thích, giữ schema/ledger.
   Không downgrade schema hoặc restore đè dữ liệu phát sinh. FACE_ONLY đổi chính sách phải được thông báo khi release.

**Cần duyệt tiếp:** xuất bản gói mới; sau CI đạt mới xem xét merge/deploy/migration/flags/environment riêng.
Không đánh dấu hoàn thành mã nguồn/production khi CI512 và PR còn bị chặn.

## Chốt kiểm chứng local — PASS; Linux/production vẫn BLOCKED

| Kiểm tra cuối | Kết quả | Bằng chứng local ignored |
| --- | --- | --- |
| Full suite, PostgreSQL test, parallel4 | **696/696 PASS, 415.755s** | final-regression-passing.log |
| Regression sau sửa endpoint khóa lồng nhau | 40/40 PASS,11,110s | final-face-guards-regression.log |
| Migration drift + Django check | PASS,0issues/No changes | final-system-check-last.log;final-migration-drift-last.log |
| collectstatic DEBUG=False --clear | PASS,manifest tạo thành công | final-collectstatic-complete.log |
| pip check / bash -n / node --check | PASS trên Windows/Git Bash; chưa phải Linux build | phiên kiểm tra local |
| Migration0021→0024,OFF/OFF/ON | PASS,27 HTTP200; DB test đã dọn | FINAL_MIGRATION_REHEARSAL.json |
| Camera/API simulated | 11/11 PASS,bao gồm từ chối quyền camera | final-face-js-qa.json |
| Responsive320–1440 | 56/56 PASS,0JS/asset error | final-browser/browser-results.json |
| Wheel metadata Linuxx86_64/CPython3.14 | 23/23 có wheel;không phải cài/build | FINAL_LINUX_WHEEL_AUDIT.json |
| Source GPS/Map/demo reference audit | Không còn các tham chiếu active đã tìm | rg audit customers/templates/static/restaurant_system |
| Gói thay đổi/secret scan | PASS;không env/dump/modelbinary/cache | FINAL_UPGRADE_REVIEW_MANIFEST.json |
| CI Ubuntu mới /512MiB thật | BLOCKED,chưa chạy | workflow chuẩn bị,chưa publish |
| Render/iPhone thật | BLOCKED,chưa deploy/thiết bị thật | không dùng mô phỏng thay nghiệm thu |

Lượt full trung gian695 test có1failure: endpoint cũ và canonical cùng lấy semaphore,
trả429 khi không có request cạnh tranh. Đã bỏ guard trùng, giữ guard tại canonical;
không đổi assertion400 hay nới bảo vệ. Lượt696 cuối bao gồm regression schema membership bổ sung.
Một warning override DATABASES có chủ đích trong guard test; warning runpy settings thuộc test cấu hình.
Không giấu các lượt lỗi trong log.

Harness512 dùng `scripts.render512_settings` chỉ chấp nhận DB restaurant_ci512/127.0.0.1/RENDER=false,
DEBUG=false và static production; HTTP loopback thay TLSproxy để driver CI gửi secure-session fixture.
Production settings/cookies/SSL không thay đổi. Probe thất bại cả khi có oom hoặc oom_kill,
giữ diagnostics khi lỗi. Chưa thực thi nên không báo harness512 PASS hoặc đã đạt512.

Sau local checkpoint, SHA và hash patch nằm trong `artifacts/FINAL_UPGRADE_LOCAL_CHECKPOINT.json`.
Patch/manifest/PR-body đã chuẩn bị chỉ để review local, **không phải PR đã tạo**.
Phải có phê duyệt xuất bản phạm vi mới rồi mới push/tạo draft PR/chạy CI.
