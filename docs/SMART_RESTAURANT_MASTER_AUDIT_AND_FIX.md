# Smart Restaurant — kiểm toán, sửa lỗi và điều kiện triển khai

Tài liệu chốt theo bằng chứng trong phiên master task; chưa xác nhận production đã được sửa. Không merge main, deploy, migrate hoặc sửa dữ liệu Render. Các mục 1–11 ghi lịch sử kiểm tra ban đầu; cập nhật CI Ubuntu và cổng triển khai ngày 12/11/2026 ở mục 12 có hiệu lực thay cho các giới hạn Linux cũ.

## 1. Tổng quan và ma trận

Kiểm kê bằng Django resolver/app registry: **276 route**, **57 model customers** trong bản tích hợp có TableServiceAssignment và TableSession; không gọi đây là số API hoặc permission. Kiểm kê tĩnh thêm **393 hàm cấp module**, **35 module test** tại thời điểm đầu khảo sát và **192 template**. Số test thay đổi theo bản sửa; tham chiếu test không đồng nghĩa route đã E2E.

Ma trận từng route/view/model/service/decorator/test: [SMART_RESTAURANT_ROUTE_MATRIX.md](SMART_RESTAURANT_ROUTE_MATRIX.md). Ma trận không tự gán PASS cho các route chỉ có code. Phân hệ: auth/RBAC, khách/booking/cọc, POS/bếp/kho, hóa đơn/thanh toán/loyalty, nhân sự/ca/chấm công/lương, AI/chatbot/RAG/dự báo/gợi ý/GA/FaceNet, GPS/map và Channels.

| Phân hệ | Bằng chứng và hiện trạng | Mức xác nhận |
| --- | --- | --- |
| Auth, CSRF, RBAC | Có unit/integration/HTTP tests; thêm shared object scope | Local regression; production chưa hậu kiểm |
| Booking | Khung giờ, sức chứa, khu vực, bàn cụ thể, hold expiry, lock và concurrency; thêm giờ mở/đóng | Local/test DB |
| Check-in và phục vụ | BookingVisit hiện hữu; TableSession giữ trạng thái vật lý tới khi trả bàn | Code + test mới; migration chưa production |
| Phân công | 0022, ca APPROVED, nhân viên active, audit đổi người | Flag ON/OFF trong test; production OFF chưa nghiệm thu |
| Bếp/kho | READY trừ kho theo món, idempotency/concurrency, NO_RECIPE rõ | Hồi quy hiện hữu; không tạo order production |
| Tài chính | Cọc áp dụng vào Invoice, thu bổ sung, webhook signature/idempotency/late reconciliation | Tests, không giao dịch Stripe thật |
| Nhân sự/lương | Ca nháp/duyệt/hủy, ownership attendance, payroll locked | Hồi quy; không xếp ca production |
| FaceID | Model hash/version, JSON lỗi, GPS/ca độc lập, engine smoke Windows | Không phải nhận diện người thật hoặc chống replay đã kiểm định |
| GPS/OpenFreeMap | Marker nhân viên, nhà hàng cố định ADMIN-only, nền thật localhost | Browser mô phỏng GPS; thiết bị thật/Render BLOCKED |
| AI dự báo/gợi ý | Artifact có provenance REAL+SYNTHETIC | Nghiên cứu, chưa dự báo kinh doanh đã kiểm định |
| RAG | Artifact/index có metadata, thiếu asset có lỗi/fallback | Không xác nhận runtime/RAM Render đủ cho mô hình nặng |
| Realtime | Reauthorize session/permission; thêm scope event theo đơn/hóa đơn | Test local; multi-process Redis production chưa xác minh |
| Scheduler | Có expire_booking_deposits, allocation bỏ hold hết hạn ngay khi đọc | Production schedule chưa xác minh |

## 2. Nguyên nhân và sửa lỗi thực tế

### Vòng đời bàn

Order COMPLETED trước đây tự chuyển booking sang COMPLETED và bàn AVAILABLE; nó chỉ chứng minh món xong/đơn sẵn sàng xuất hóa đơn. Đã bỏ side effect đó. Thêm TableSession liên kết bàn với booking/order; chỉ một phiên mở mỗi bàn, thời điểm bắt đầu/kết thúc, người kết thúc và lý do. BookingVisit vẫn là thông tin khách đến/không đến, không dùng như một lần trả bàn giả.

Luồng mới khi bật lifecycle: check-in → session → mở đơn idempotent → bếp → Order COMPLETED → invoice/payment → xác nhận khách đã rời và trả bàn. READY/PAID không tự trả bàn. Khách quá giờ tiếp tục chiếm bàn. Walk-in kiểm tra reservation và phiên đang dùng dưới khóa Area → Table; không chiếm booking hợp lệ.

Chỉ trả bình thường khi đơn COMPLETED và invoice PAID, có checkbox xác nhận và lý do. Quản lý có quyền có thể kết thúc phiên treo bằng override có lý do/AuditLog, không đổi tiền thành đã nhận hoặc tự hoàn tiền. Đơn cũ còn pending sau override không được thêm/chế biến tiếp vào phiên đã kết thúc; tài chính vẫn phải đối soát riêng. Không tự đóng phiên production hoặc backfill lịch sử đã hoàn thành.

### Object scope

Trước sửa, staff có view/change_order có thể truy cập đơn bàn khác qua ID; danh sách, chi tiết, service, tài chính và socket không dùng cùng một scope. `service_scope.py` được dùng trong orders/bookings/invoices/payments/tables, HTTP GET/POST/partial, generic Django admin read-only, báo cáo, order/kitchen/commerce/payment services và reauthorization WebSocket. Event toàn bếp/thanh toán kiểm tra đối tượng trước gửi cho STAFF. Chat/inventory giữ quyền chuyên biệt của chúng.

**Gating tương thích:** scope theo phân công áp dụng khi TABLE_SERVICE_ASSIGNMENTS_ENABLED=true. OFF giữ phạm vi quyền mô hình cũ để code có thể deploy trước khi bảng 0022 tồn tại. OFF không được nghiệm thu như “STAFF đã được cô lập theo bàn”. ADMIN/MANAGER vẫn phải có capability hiện hữu, không tự cấp permission. Khi bật, chưa có phân công thì không thấy/tác động bàn ngoài phạm vi. Tài khoản customer vẫn theo ownership riêng.

Che tên/ghi chú khách trong trang Order/Invoice/Receipt khi không có view_booking; không dùng việc chỉ ẩn nút để thay xác thực server. Trang chỉnh nhân viên/lịch/lương yêu cầu role quản lý cùng permission, không cho STAFF dùng quyền gán nhầm để sửa đồng nghiệp.

### Tài chính và dữ liệu

Báo cáo cũ chỉ tổng Payment SUCCEEDED, không thể hiện cọc trả toàn bộ hoặc thu bổ sung. Thêm đối chiếu riêng: thu cọc, thu bổ sung, tổng tiền thu gộp chưa trừ hoàn tiền, doanh thu Invoice PAID, cọc đã áp dụng và phần còn cần đối soát. Không cộng cọc lần nữa vào doanh thu hóa đơn. Test số liệu 30 cọc +70 bổ sung =100 thu,100 doanh thu; không phải130. Không tự tạo ledger hoàn tiền hoặc gọi hoàn tiền Stripe thật.

Booking kiểm tra toàn bộ khoảng nằm trong giờ hoạt động của RestaurantInfo active, có xử lý qua đêm. Chặn quá khứ giữ nguyên. Sửa test qua nửa đêm lấy date/time cùng một instant, không nới validation.

## 3. File chính

- Mới: service_scope.py, table_session_models.py, table_session_service.py, table_session_views.py, migrations/0023_table_service_session.py, test_master_service_safety.py, management/commands/audit_system_readiness.py.
- Sửa: order_service, kitchen_service, booking_service, booking_advanced_service, commerce_service, payment_service, report_service; business/management/operations/payment views; consumers, admin, table_availability, table_board, pos_presentation; settings/urls và template Order/Invoice/Receipt.
- Test hợp đồng được cập nhật: test_operations (trả bàn rõ ràng), test_service_assignment_flow (thanh toán rồi trả bàn), test_module02 (fixture thời gian qua nửa đêm).
- Không mang những dirty changes khác trong workspace gốc: Stripe scripts, dashboard tối ưu cũ, AI cache và các patch chưa review. Không xóa chúng.

## 4. Dữ liệu và backup

Backup custom-format mới của **cả local và Render**, SHA-256 và decode PASS. Đã diễn tập pg_restore vào **hai database LOCAL test tạm**, restore_exit=0: mỗi archive có66 bảng, local1812 dòng, Render1638 dòng tại snapshot backup; FK chưa validate=0, tài khoản ADMIN Manh0508 hiện diện. Database test tạm được xóa sau kiểm tra; không xóa database nghiệp vụ nào. Số dòng gồm session/metadata và không thay thế số1196 dòng đã nhập trước đây.

Chi tiết private: artifacts/MASTER_BACKUP_VERIFICATION.json, MASTER_RESTORE_REHEARSAL.json. Dump giữ trong database_backups đã ignore, không đưa vào Git. Snapshot mới phải được lấy lại ngay trước thao tác production vì dữ liệu có thể phát sinh sau lần backup này.

Đối chiếu SELECT trước đó: Render20 bàn/26booking, gồm6 hủy,10 lịch sử,10 hold tương lai hết hạn; không tạo order để lấp sơ đồ. Migration 0022/0023 chưa được áp dụng lên source local hoặc Render trong tác vụ này. Migrate --plan local chỉ đọc thấy đúng hai CreateModel. SQL 0023 ở artifact master-session-sql.log.

## 5. Migration và rollback

- 0022: phân công theo ca. 0023: TableSession, FK PROTECT, one-to-one booking/order, partial unique một phiên mở/bàn, check session có booking/order và ended_at>=started_at.
- Không RunPython/backfill/seed. Chống concurrent bắt đầu phiên qua khóa bàn + unique DB; chỉ sửa schema trên test DB trong quá trình tests.
- TABLE_SERVICE_ASSIGNMENTS_ENABLED=false và TABLE_SERVICE_LIFECYCLE_ENABLED=false mặc định; không truy vấn các bảng mới ở đường flag OFF đã kiểm thử.
- Rollback transaction trả bàn phải giữ session/table/booking/audit đồng bộ. Rollback triển khai không reverse migration có dữ liệu: reverse sẽ DROP bảng mới.
- Không tự restore đè production. Giữ bảng/session/audit và ưu tiên sửa tiếp. Tắt assignment flag làm trở lại scope cũ, nên **không coi việc tắt cờ đơn lẻ là rollback bảo mật đã nghiệm thu**. Nếu cần rollback sau bật, chủ hệ thống phải duyệt cửa sổ hạn chế truy cập và phiên bản rollback, đối chiếu phiên đang mở trước khi mở lại phục vụ.

## 6. AI, recipe, performance

Kiểm kê local45 món,10 thiếu recipe: artifacts/MASTER_RECIPE_COVERAGE.md. Code kho giữ NO_RECIPE, không trừ theo phỏng đoán; food_cost thiếu recipe/giá trả None và trạng thái chưa đủ dữ liệu. Chưa tự bổ sung công thức hoặc đổi dữ liệu production. Chưa kiểm định toàn bộ topping cost/yield từ dữ liệu thực; không quảng bá tỷ lệ giá vốn là số kế toán chính xác.

Artifact forecast/recommendation trong Git ghi1 ngày thật/69 ngày mô phỏng,5 tương tác thật/275 mô phỏng. Giao diện forecast có provenance; kết quả là nghiên cứu, không đủ chuỗi kinh doanh thật để nghiệm thu forecast thực tế. Không train hoặc seed thêm. Chatbot/index/metadata hiện diện local, chưa chứng minh embedding cache/RAM trên Render. Không xóa artifact hoặc module chỉ vì ít dùng.

FaceNet/MediaPipe Windows smoke: khởi tạo4,568s; tensor128 chiều0,209s; processRSS309,69MiB, CPUExecutionProvider. Đây không phải test danh tính và không đại diện tổng RAM Render. Hash/model_version giữ nguyên; threshold vẫn provisional nếu chưa có tập hiệu chỉnh. FAR/FRR/replay attack với thiết bị thật chưa kiểm định.

Thư mục SmartRestaurant_Submission chứa bản source nộp lặp được Git theo dõi; không tự xóa. Build/start root dùng restaurant_system.asgi, không chạy entrypoint trong bản sao. Cần chủ đồ án review riêng nếu muốn bỏ bản nộp; chưa tuyên bố toàn bộ không được dùng.

## 7. Kiểm thử và giới hạn

- System check, makemigrations --check --dry-run và collectstatic DEBUG=False: PASS trong các lượt ghi log.
- Full trung gian656/656 PASS,244,445s; focused35/35 PASS,6,830s. Không dùng số này thay full cuối sau những thay đổi mới.
- Full kế tiếp657 test có1 failure ở test quá khứ khi qua nửa đêm; nguyên nhân fixture ghép sai ngày/giờ, đã sửa và chạy lại full. Kết quả cuối được bổ sung sau khi lệnh hoàn tất.
- Sau sửa fixture: full **657/657 PASS,159,501s**. Sau đó UI20/20 PASS4,656s và scope15/15 PASS4,165s; lượt release-candidate chạy lại toàn bộ sau kiểm tra rollback/audit và phân quyền sơ đồ được ghi ở cuối. Không cộng các lượt focused vào full để tạo số test giả.
- Browser6 trang ×7viewport320/375/390/412/768/1024/1440 =42/42,0 exceptionJS/assetHTTP lỗi/overflow; gồm yêu cầu nhập lý do/checkbox trả bàn, GPS marker và chỉnh sửa ADMIN. HTML/view fixture DB test, static và OpenFreeMap thật; camera/GPS/API mô phỏng, không phải E2E vật lý hoặc production.
- Financial/FaceNet/GPS/Stripe integration dùng DB test, các provider/inference được mock theo từng test. Không suy từ mocks ra dịch vụ thật đã chạy.
- Linux dependency dry-run cuối exit0, giải101 distributions toàn wheel cho CPython3.14/manylinuxx86_64. Không cài vào production; không phải Linux runtime/build test. WSL stub hiện diện nhưng báo chưa cài WSL, Docker không có.

## 8. Điều kiện Render và các bước cần phê duyệt

**Chưa đủ bằng chứng để triển khai production.** Không có Render connector/API credential để xem Auto-Deploy, service branch, metrics/logs hoặc scheduler. Chưa thay Environment, Build/Start Command, secret, domain hoặc PostgreSQL.

1. Chủ hệ thống duyệt các PR/commit và thứ tự tích hợp. Không merge main cho tới khi đã biết Auto-Deploy vì merge có thể tự kích hoạt build.
2. Dashboard Render: xác nhận đúng Web Service/domain/branch, Auto-Deploy enabled/disabled, pending deployment và commit hiện chạy. Nếu muốn tắt Auto-Deploy để kiểm soát thứ tự, đây là thay đổi production cần duyệt riêng.
3. Lấy backup cuối, archive verification và đối chiếu count/migrations/phiên đang dùng. Không tạo bản ghi để làm đẹp.
4. Review0022→0023 SQL/plan và cửa sổ thay schema. Deploy code tương thích với cả hai flag false; Linux build bash build.sh; start daphne -b 0.0.0.0 -p $PORT restaurant_system.asgi:application. Không chạy migrate trong build.sh.
5. Sau phê duyệt schema riêng mới migrate; kiểm tra constraints và trạng thái legacy. Không tự biến lịch sử thành TableSession hoặc gán ca production. Bật lifecycle/phân công sau duyệt, quản lý giao bàn thật; kiểm tra scopeSTAFF A/B và trả bàn.
6. Redis: nhiều process/instance phải có CHANNEL_REDIS_URL. InMemory chỉ bảo đảm trong cùng process; chưa xác minh topology Render, không tự tạo dịch vụ trả phí.
7. Scheduler: command expire_booking_deposits chạy mỗi phút, không --stripe nếu chưa duyệt thao tác provider. Cần owner duyệt scheduler phù hợp chi phí (Render Cron/dịch vụ hiện có); chưa tự đăng ký. Không dùng thread trong web request để giả scheduler. Allocation đã bỏ hold hết hạn nên không phụ thuộc job để tránh double-book, nhưng nhãn DB và provider cleanup vẫn cần job.
8. Không tự thêm job xóa FaceChallenge/chat/GPS/audit khi chưa duyệt retention. Dọn dữ liệu pháp lý, hoàn tiền, thay credential/quyền đều cần phê duyệt cụ thể.
9. Hậu kiểm production thật: health/HTTPS/static, model/hash/version/init/RAM, worker OpenFreeMap, quyền/CSRF/WebSocket, booking/cọc, GPS/iPhoneAndroid và smoke chỉ đọc. Test giao dịch/chấm công/đơn mới dùng staging/test; không tạo tiền hoặc dữ liệu giả trên production.

## 9. BLOCKED và việc còn lại

| Điều kiện | Trạng thái | Lý do/phạm vi |
| --- | --- | --- |
| Tích hợp hai PR, sửa ưu tiên | CODE/LOCAL TEST | Không merge main |
| Backup và restore rehearsal local | PASS | Chưa restore production |
| Linux wheel resolution | PASS | Không chứng minh libGL/MediaPipe/runtime Linux |
| Auto-Deploy/Render logs/build/metrics | BLOCKED | Thiếu quyền/credential Render |
| Linux clean build thực tế | Đã có CI Ubuntu | Xem bằng chứng mới ở mục12; vẫn chưa build/deploy Render |
| Thiết bị iPhone/Android/FaceNet thật | BLOCKED | Không có thiết bị/camera dataset kiểm định |
| Dự báo từ chuỗi dữ liệu thật đủ dài | BLOCKED | Artifact chủ yếu synthetic, không tạo dữ liệu giả |
| Scheduler/Redis production | BLOCKED | Thiếu topology/config và duyệt chi phí/thay đổi |
| Refund provider thực/retention pháp lý | NOT EXECUTED | Không ủy quyền giao dịch/xóa; cần quy trình riêng |
| Full final + migration/browser | Ghi theo log cuối | Không lấy số test che thiếu E2E production |

Không đánh dấu toàn bộ hệ thống đạt nghiệm thu chỉ từ full suite. Ma trận route mô tả code/test references; nhiều phân hệ mới chỉ được regression qua test, chưa E2E mọi màn hình và thiết bị thật. Báo cáo này và checkpoint ghi rõ phần hoàn thành/phần chưa xác nhận để chủ hệ thống review.

## 10. Git và thứ tự review

Main được kiểm tra lại: b170842ce9ba0d58bbffb9517e7ade0a054ab284. PR #2 vẫn open tại9d02c23, PR #3 open tại1f68568, chưa merge. Nhánh integration/master-readiness gồm hai merge local để kiểm thử, không phải merge vào main; base tích hợp3107bbd21026180773598b9f3e616bbbde68d0a9. Nhánh fix/master-service-audit chứa các sửa master task mới. Workspace gốc vẫn được giữ nguyên, không stage tất cả dirty files của người dùng.

PR mới nên review diff so với integration/master-readiness để không lặp hai gói đã review. Khi chủ hệ thống duyệt #2/#3 và tích hợp chính thức, kiểm tra/rebase nhánh sửa lên main tương ứng và chạy lại checks trước merge. Không coi trạng thái mergeable hoặc draft PR là phê duyệt triển khai. Không bật auto-merge.

Ảnh và bằng chứng local: artifacts/master-browser/{customer,staff,order,gps,location,schedule}-{390,1440}.png; browser-results.json, MASTER_LOCAL_INVENTORY.json, MASTER_FUNCTION_INVENTORY.json, MASTER_AI_ARTIFACT_AUDIT.json, MASTER_LINUX_DEPENDENCY_SUMMARY.json. Các artifact ignored không đưa dữ liệu thật hoặc backup lên PR; tài liệu route matrix chỉ có code reference.

## 11. Kết quả chốt để review

- Full release-candidate **658/658 PASS,189,884s** (`booking-gps-masterreleasecandidate-tests.log`), PostgreSQL test riêng, gồm migration0022/0023 và core/UI cuối. Hai test socket mới bổ sung sau full discover: lượt focused **11/11 PASS,8,299s**, gồm HTTP/service/finance/rollback, socket chéo bàn và thu hồi khi hủy lịch. Không gọi đây là full660 test đã chạy.
- Browser chạy lại cuối **42/42 PASS**, sáu trang/seven viewport, không JS/asset lỗi hoặc tràn ngang. Đã sửa wrap tiêu đề mã Order dài và khóa nút trả bàn thường khi chưa đủ điều kiện, hiển thị lý do. GPS/camera mô phỏng, OpenFreeMap nền thật.
- Linux pip dry-run cuối exit0,101 package wheel; check/drift/collectstatic PASS. Không WSL/Docker Linux thực tế; không production build.
- Backup local/Render và restore rehearsal local PASS; backup private, không upload. Git staged36 file mới/sửa, secret/path scan và diff whitespace PASS.
- Không merge main, deploy, migrate, bật flag hoặc đổi dữ liệu production. **Trạng thái: sẵn sàng review gói sửa ưu tiên; chưa đủ điều kiện nghiệm thu toàn hệ thống hoặc triển khai production.** Những giới hạn BLOCKED/chưa kiểm chứng ở trên vẫn áp dụng, không được bỏ qua chỉ vì test PASS.

Draft review: [PR #4](https://github.com/NguyeDucManh/QuanLyNhaHang/pull/4), base integration/master-readiness. Sau commit đầu, kiểm tra thêm phát hiện danh sách thanh toán vẫn có tên khách và tìm kiếm bằng tên khi thiếu view_booking. Đã che ở payment list/receipt, giới hạn search và thêm HTTP assertion; **73/73 tests tài chính/Stripe/quyền PASS,20,898s** (`booking-gps-masterfinancialprivacy-tests.log`). Đây là lượt targeted sau full658, không báo full660 hoặc cộng73 vào full. Gói cuối37 file mới/sửa so với base tích hợp; không thay PR #2/#3 hoặc main.

## 12. Cập nhật CI và readiness — 12/11/2026

### Git và tích hợp

Đã đọc trạng thái GitHub: #2/#3 open, chưa merge, vẫn dựa trên main; #4 draft dựa trên integration/master-readiness. Không sửa nhánh #2/#3. Nhánh #4 thêm CI Ubuntu, operational-readiness command/tests, guard thư viện native, bộ cài CPU Linux và runbook. Không đưa dirty changes của workspace gốc, .env, database dump, AI binary/cache vào nhánh.

Đã diễn tập trên worktree riêng: squash #2 → squash #3 → cherry-pick chỉ commit riêng #4 sau3107bbd. Cây mã nguồn khớp nhánh ứng viên, không conflict/mất thay đổi, main không đổi. Đây là diễn tập local, không phải merge GitHub. Sau owner merge #2/#3 phải lấy main mới, replay phần riêng #4, đối chiếu cây và chạy CI lại. Quy trình chi tiết: [RENDER_INTEGRATION_RELEASE_RUNBOOK.md](RENDER_INTEGRATION_RELEASE_RUNBOOK.md).

### CI đã thực thi trên Linux

[Run Ubuntu thành công đầu tiên](https://github.com/NguyeDucManh/QuanLyNhaHang/actions/runs/43071213008), code06cef54, Ubuntu24.04/Python3.14.8/PostgreSQL17/Redis7:

- Cài production requirements và pip check PASS; Django checks/drift PASS.
- Schema0021/flagsOFF/public GET PASS; áp dụng0022/0023, reverse và áp dụng lại PASS trên **DB CI rỗng**. Không làm tương tự production.
- Scheduler cọc chạy trên DB CI; không gọi Stripe thật hoặc production.
- Hai model thật tải đúng SHA-256, engine FaceNet+MediaPipe ready, CPUExecutionProvider, tensor128 chiều. Load0,943s, tensor0,028s; peakRSS595516KiB (khoảng582MiB). Không phải test danh tính người thật hoặc đo RAM Render.
- `bash build.sh` DEBUG=False PASS;241 static source,969 post-process.
- Full **664/664 PASS,116,382s**; hai Redis channel-layer client gửi/nhận thật PASS, readiness flagsON/Redis PASS.

Windows full trên worktree tách biệt: **664/664 PASS,163,382s** (`booking-gps-ci_full_verified-tests.log`), sau sửa test tìm kiếm theo quyền. Test này kiểm tra cả việc không thể dùng tên khách làm search oracle khi thiếu view_booking và tìm kiếm thành công khi được cấp quyền; không nới quyền production.

Lỗi CI đầu tiên là smoke schema cũ thiếu django_session: thêm migrate sessions vào DB CI. Lỗi tiếp theo đã có traceback chính xác: MediaPipe thiếu `libEGL.so.1`; CI cài libegl1/libgles2, build nạp native runtime thật trước khi tiếp tục. Không đổi model_version/threshold/GPS hoặc bỏ qua nhận diện.

Sau run06cef54, bộ cài Linux được tối ưu sang wheel PyTorch CPU chính thức2.14.1+cpu cùng phiên bản2.14.1; CI có tensor smoke và assert không có CUDA. Cache CPU được tách khỏi cache tải CUDA cũ. **Run06cef54 không được dùng làm bằng chứng cho thay đổi sau nó**: xem Checks của SHA mới nhất tại [PR #4](https://github.com/NguyeDucManh/QuanLyNhaHang/pull/4) hoặc [lịch sử Actions](https://github.com/NguyeDucManh/QuanLyNhaHang/actions?query=branch%3Afix%2Fmaster-service-audit). Kết quả mới nhất cũng lưu local ở artifacts/CI_LINUX_LATEST.json; chỉ conclusion=success với mọi bước test thực sự chạy mới đạt cổng CI.

### Readiness và phần chưa xác minh

`check_operational_readiness` chỉ đọc PostgreSQL bằng transaction READ ONLY, kiểm tra schema theo flags, checksum map vendor, backlog cọc chưa xử lý, legacy occupied/orders và Redis PING nếu được cấu hình. `--require-enabled` không cho coi flagsOFF là đã bật scope; `--require-redis` từ chối InMemory. Nó luôn báo external_schedule_verified=false: có command không chứng minh cron đang chạy. Backlog chỉ đếm booking PENDING_DEPOSIT đã hết hạn, không gộp booking đã hủy.

Render connector chưa được kết nối, không có Render API credential trong môi trường. Đã kiểm tra khả năng công cụ, **chưa đọc được Auto-Deploy, branch, Build/Start, logs, metrics, Redis topology hay cron production**. Không suy enabled/disabled từ GitHub. Plugin Render được đề xuất để chủ tài khoản kết nối; chưa thay cấu hình.

Public probe phiên này: health/staticCSS/staticJS Render đều ReadTimeout40s; OpenFreeMap style200 application/json. Không quy lỗi timeout cho cold start/OOM khi chưa có logs, không tuyên bố website đã deploy bản mới. OpenFreeMap từng được browser kiểm tra thật ở localhost; chưa có iPhone/Android phần cứng hoặc hậu kiểm Render mới. Không gửi ảnh khuôn mặt, tạo challenge, đơn hàng, chấm công hoặc thanh toán production.

Backup và restore rehearsal tại mục4 vẫn là bằng chứng có thực; phải lấy snapshot cuối mới ngay trước cửa sổ production được duyệt. Hai feature flags giữ mặc địnhfalse. CI dùng PostgreSQL/Redis tạm và fixture secret riêng, không nhận credential Render, không có bước deploy.

### Phê duyệt còn cần

1. Cấp kết nối Render hoặc đối chiếu Dashboard để chốt Auto-Deploy/currentSHA/topology trước merge main; mọi thay đổi setting cần duyệt.
2. Duyệt thứ tự merge #2→#3→#4 sau CI đúng SHA; duyệt deploy tương thích flagsOFF và điều kiện EGL/GLES/RAM thực tế. Không tự nâng gói hay tạo dịch vụ có phí.
3. Sau backup cuối, duyệt migration0022→0023 riêng; sau đó mới duyệt bật flags, Redis/scheduler và phân công dữ liệu thật.
4. Smoke production chỉ đọc, xác minh logs/hash/model/API/static/map; kiểm thử ghi trên test/staging, thiết bị iPhone/Android và nhận diện người thật vẫn cần môi trường/thiết bị được cấp.

Rollback giữ bảng/session/audit, không reverse migration có dữ liệu hoặc restore đè. Tắt assignment flag làm trở lại scope cũ, nên cần kế hoạch hạn chế truy cập được duyệt nếu rollback; không quảng bá việc tắt cờ là bảo mật đã nghiệm thu.
