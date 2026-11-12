# Release Smart Restaurant — 12/11/2026

**Release candidate đã chuẩn bị; chưa cho phép triển khai production.**
Nhánh `release/smart-restaurant-20261112`, base main `b170842ce9ba0d58bbffb9517e7ade0a054ab284`.
Mọi thay đổi release nằm trong worktree riêng. Không thay workspace nghiệp vụ, PostgreSQL Render,
environment, Auto-Deploy, domain, gói RAM, threshold/liveness hoặc quyền tài khoản thật.

## Tích hợp và kiểm chứng

Main được fast-forward trên **nhánh release riêng** tới PR5 `8c6cff45c28d78ba64bb0407e40ce12c316a359a`.
Ancestry Git xác nhận toàn bộ head PR2 `9d02c233…`, PR3 `1f685682…`, PR4 `10d7560…`, PR5 `8c6cff4…`
đều là ancestor của release. Không cherry-pick/squash/merge lại từng PR; không merge vào main.
Phần bổ sung release chỉ là tài liệu này; tree mã ứng dụng giữ nguyên bản tích hợp đã kiểm thử PR5.
Draft Release PR vào main là đơn vị review/deploy dự kiến; giữ các PR cũ chưa merge/chưa đóng.
Sau phê duyệt, đưa release vào main một lần; không merge lại chuỗi PR2–5 tạo thay đổi chồng nhau.

| Hạng mục | Kết quả/bằng chứng |
| --- | --- |
| Audit route/menu/assets release | PASS: không GPS/Map runtime reference, không Leaflet/MapLibre; 275route được kiểm kê |
| Route GPS cũ | `/management/settings/location/` và `/work/location/check/` không resolve; regression xác nhận404 |
| FACE_ONLY | PASS config/backend/UI/regression; vẫn yêu cầu đúng tài khoản/FaceID/ca APPROVED và thời gian hợp lệ |
| Khu vực/bàn | PASS test tạo/đổi tên/inactive ADMIN→CUSTOMER, capacity/overlap/concurrency; không hardcode tên khu |
| Thành viên | PASS boundary0/1.999.999/2m/5m/15m,net paid spend/refunds,voucher tốt nhất,snapshot và quyền |
| Source PR5 CI | Ubuntu696/696 PASS,134,468s; cgroup512MiB peak366,520MiB,OOM0 trên8c6cff4 |
| CI release | Bắt buộc Ubuntu + cgroup512 **trên SHA cuối của Draft Release PR**, công bố tại Checks/PR body |
| Migration trên bản sao backup Render mới | PASS tiến0022–24,lùi khi5bảng mới rỗng,tiến lại; mọi dòng cũ giữ nguyên digest |
| Production | BLOCKED: thiếu xác minh Dashboard/Shell/Auto-Deploy/RAM/native libs và phê duyệt thao tác |

Release CI sử dụng Ubuntu/PostgreSQL test/Redis, chạy build.sh, migrations tiến/lùi,
full regression với flagsOFF/ON; Docker riêng ép512MiB,không swap,1CPU/1Daphne.
Không dùng kết quả PR5 thay CI release. Kết quả SHA/runs/peak cuối được ghi trực tiếp trong Draft Release PR.
Tensor25 không phải25frame nhận diện/liveness người thật. Camera iPhone/Safari thật,FAR/FRR,
semantic RAG embedding cùng FaceNet và tải dữ liệu/concurrency production vẫn chưa nghiệm thu.

## GPS/Map và thay đổi có hiệu lực khi deploy

Không còn route/menu/template bản đồ/GPS trong ứng dụng release; không có navigator.geolocation
trong static runtime và không có MapLibre/Leaflet vendor. Lịch sử/model/migration vị trí được giữ nguyên.
Sơ đồ bàn nhà hàng vẫn hoạt động, độc lập với GIS.
**FACE_ONLY có hiệu lực ngay khi code release chạy**, không phụ thuộc ba feature flag phía dưới.
Deploy vì vậy cũng là thay đổi chính sách bỏ GPS; không hạ threshold hoặc tắt FaceID/liveness.
Không có ca được duyệt hoặc hồ sơ không hợp lệ: báo rõ và không cho chấm công.
Không tự tạo ca, tái đăng ký khuôn mặt hoặc tạo Attendance cho Manh0508 để thử nghiệm.

## Render hiện tại — kiểm tra và phần chưa thể xác nhận

GET HTTPS hiện tại: `/healthz/`, `/`, CSScustomer, JSface-realtime, robots và sitemap đều200, MIME đúng.
Lượt đo khoảng0,4–0,8s, chỉ là probe đọc hiện trạng; không benchmark Render/cold-start hoặc bằng chứng release đã deploy.
JS đang phục vụ còn geolocation, phù hợp xác nhận của chủ hệ thống rằng PR5 chưa triển khai.
Không có deployment/status GitHub đủ để xác minh SHA runtime. Không có Render tool/API credential/CLI hiện dùng được.
**Chưa xác minh** Auto-Deploy,RAM thực cấp,native libraries,Build/Start Command,environment,DATABASE_URL service,
Redis và scheduler từ Dashboard. Không suy ra chúng từ trang web hoặc cấu hình được báo trước đây.

Cấu hình đích cần đối chiếu, chưa tự chỉnh:

```text
Branch: main
Runtime: Python (không chuyển sang Dockerfile.ci512)
Build Command: bash build.sh
Start Command: daphne -b 0.0.0.0 -p $PORT restaurant_system.asgi:application
RAM: xác minh thực tế; CI đã kiểm thử cgroup512MiB
Auto-Deploy: phải đọc trạng thái thực tế TRƯỚC merge
```

Native diagnostics dự kiến chỉ đọc sau khi có quyền Shell:

```bash
python scripts/check_face_native.py
python manage.py check_face_runtime --load-engine
python manage.py check_operational_readiness
```

Build phải fail rõ nếu thiếu native EGL/GLES/GL/PortAudio/libgomp hoặc model/hash; không bỏ qua check.
`build.sh` không migrate/seed/train. CI có native packages không chứng minh image Python của Render đã có chúng.
Nếu thiếu, dừng rollout để chốt cách cài phù hợp môi trường được chủ hệ thống duyệt, không tự đổi runtime/gói trả phí.

## Backup mới và phục hồi thử — PASS

Mốc backup `release-readiness-20261112T083543Z`, lưu trong `database_backups` Git-ignore;
không upload archive, nội dung dữ liệu, mật khẩu hoặc vector khuôn mặt lên GitHub.

| Archive | Byte | SHA256 |
| --- | ---: | --- |
| local-full.dump | 392322 | bd1c31421407df32db5af48b1e51c1570b9465ea8b1a10ad410942b7f748013f |
| render-full.dump | 394436 | 40e0ef2fd516dbcb4c875aec9ccde5ba19952e29ea41b15362de8bd5314489d9 |

Hai archive đều đọc TOC/giải mã toàn bộ và **restore thực tế vào DB test local riêng** thành công:
local66bảng/1.813dòng; snapshotRender66bảng/1.638dòng; FK chưa validate0,ADMIN hiện diện.
DB test đã được gỡ đúng tên/prefix; không DROP/restore/truncate dữ liệu nguồn hoặc Render.
pg_dump dùng snapshot nhất quán của từng DB; inventory đọc riêng không được coi là cùng snapshot dump.
Backup logical dùng no-owner/no-privileges, không sao lưu role/password PostgreSQL cấp server/ACL managed của Render.
Tài khoản/quyền Django nằm trong archive và được kiểm tra bảo toàn.
Đây là backup thời điểm chuẩn bị; cần backup mới sát cutover nếu dữ liệu đã thay đổi.

## Đối chiếu DB và migration0022–0024

Render đã xác minh qua SSL verify-full/TLS1.3/256bit, transaction read-only:
66bảng,migration customers tới0021;20bàn,26booking,1order;
Manh0508 active/staff/superuser và nhómADMIN giữ nguyên. Không có FK chưa validate.
Snapshot backup có4FaceProfile cùng model_version`1c69044bdbf849aa58fb27df62fe0cc0d23648411192c6f63e8b764033b552a6`,
60embedding/128chiều, tương thích hash model đã pin của release; không xuất vector/hash mật khẩu.

| Migration | Thay đổi | Ràng buộc và điểm review |
| --- | --- | --- |
|0022|CreateTableServiceAssignment|FKPROTECT user/table/schedule,window dương,unique có điều kiện và index thời gian |
|0023|CreateTableSession|1phiên mở/bàn,OneToOne booking/order,ít nhất một liên kết,end>=start,FKPROTECT |
|0024|CreateMembershipPolicy/Discount/InvoiceRefund|singleton policy,OneToOne order,refund reference unique,amount checks,FKPROTECT |

Chỉ CREATE model/index/constraint; không RunPython/seed/backfill/UPDATE/DELETE business data.
Schema mới có5bảng, ban đầu rỗng. Auth contenttypes/custom permissions vàdjango_migrations sẽ tăng theo Django;
không đòi tổng số dòng DB sau migration bằng số cũ. Đối chiếu **dòng nghiệp vụ, account/hash/quyền/session cũ**.
Rehearsal dùng backup Render mới, digest toàn bộ từng bảng gốc (trừ3bảng metadata thay đổi theo migration)
giữ nguyên qua tiến/lùi/tiến. SQL từng migration và logs lưu private artifacts.
DDL atomic; thêmFK có thể lấy lock bảng tham chiếu dù bảng mới rỗng. Chốt cửa sổ triển khai,
lock_timeout5s/statement_timeout120s cho phiên migrate; nếu timeout rollback và điều tra, không ép tiếp.
**Không reverse migration production sau khi có dữ liệu mới** vì reverse sẽ DROP bảng.

## Feature flags và kế hoạch kích hoạt

Defaults trong mã và rehearsal:

```text
TABLE_SERVICE_ASSIGNMENTS_ENABLED=false
TABLE_SERVICE_LIFECYCLE_ENABLED=false
MEMBERSHIP_DISCOUNTS_ENABLED=false
```

Phải xác minh/đặt OFF trên Render theo phê duyệt; defaults mã không chứng minh environment thực tế OFF.

| Giai đoạn | Điều kiện trước bật | Kiểm tra sau bật |
| --- | --- | --- |
|Assignments|0022 sẵn,nhân viên active/ca APPROVED thực tế,quyền quản lý đúng|bàn chưa giao ghi Chưa phân công;STAFF chỉ thấy phạm vi được giao;đổi có audit |
|Lifecycle|0023 sẵn,soát active orders/occupied tables/checked-in tại cutover|booking arrival→Order duy nhất→kitchen/stock→paid→xác nhận trả bàn;legacy session cần quản lý đối soát |
|Membership|0024 sẵn,review policy,capability riêng cho MANAGER nếu được duyệt|net spend/refunds,tier,snapshot,best voucher;không đổi invoice cũ hoặc tự gọi refund provider |

Snapshot hiện tại activeorders0/occupiedtables0/checked-in0, nhưng phải đo lại lúc bật;
không backfill phiên/phân công hoặc tự tạo dữ liệu để đạt readiness.
Sau bật đủ ba cờ và cấu hình Redis đã duyệt:
`python manage.py check_operational_readiness --require-enabled --require-redis`.
Lệnh chỉ đọc; external scheduler vẫn cần bằng chứng riêng, không suy ra đã chạy từ command hiện diện.

## Cọc hết hạn và scheduler — cần phê duyệt dữ liệu riêng

Read-only hiện ghi nhận **14 cọc quá hạn chưa xử lý**. Chưa chạy expiry hoặc đóng phiênStripe.
`expire_booking_deposits` **không phải dry-run**: có thể đổi Booking→CANCELLED,Deposit→EXPIRED và tạoAudit.
Không chạy trong build/auto deploy. Cần chủ hệ thống duyệt rõ catch-up14dòng đủ điều kiện và lịch chạy định kỳ.
Không dùng `--stripe` khi chỉ duyệt expiry DB; option đó còn gọi provider và cần phê duyệt riêng.
Không biến26booking lịch sử thành Order/đang phục vụ để làm đẹp sơ đồ bàn.

## Thứ tự triển khai đề xuất — chưa thực hiện

1. Đọc Dashboard thực tế, xác minh Auto-Deploy/branch/runtime/RAM/env/native/DB/Redis/scheduler,running SHA.
2. Chủ hệ thống duyệt cửa sổ triển khai và thay đổi config cần thiết. Nếu Auto-Deploy OnCommit,
   phải chốt kiểm soát rollout trước merge: tạm dừng theo phê duyệt hoặc hoàn tất mọi gate OFF/build trước merge.
3. Backup mới sát cutover, kiểm tra archive/hash; review migrationSQL/locks/target DB và plan.
4. Chỉ khi CI release trên SHA cuối PASS và được duyệt: đưa release vào main một lần; chưa tự merge các PR cũ.
5. Deploy code với ba flagOFF. Xác minh build SHA/modelhash/native/static/health/login, không migrate tự động.
6. Sau phê duyệt migration0022–24 mới chạy đúng migration còn thiếu với timeout giới hạn; so sánh counts/digests/FK/quyền.
7. Đọc readiness flagsOFF, kiểm tra public/own-account/admin/staff; không tạo giao dịch/chấm công giả.
8. Sau phê duyệt từng flag: bật và smoke theo bảng trên; việc tạo/phân ca/phân bàn thực tế là thao tác nghiệp vụ riêng.
9. Sau phê duyệt scheduler/catch-up: xử lý đúng cọc đủ điều kiện, theo dõi audit; không tự hoàn tiền/đóngStripe.
10. Theo dõi RAM/CPU/timing/5xx/OOM và đúng SHA; chỉ đánh dấu production PASS sau kiểm tra website/thiết bị thật.

## Smoke test và rollback

Read-only production: home/menu/dish/robots/sitemap,static200+MIME,health,routeGPS cũ404,
menu không linkGPS,FaceUI hiển thị đúng ca/quyền,booking chọn area/table,member rõ trạng thái khi ưu đãiOFF.
Đăng nhập tạo session/last_login: chỉ dùng phiên QA được duyệt,không reset mật khẩu/đổi quyền.
Camera/quality/verify người thật có thể ghi FaceChallenge/FaceAudit; phải có phiên kiểm thử được đồng ý.
Booking→cọc→nhận bàn→order→kitchen→stock→invoice→payment→release và chấm công vào/ra
chạy trên staging/test DB riêng. Production business writes/Stripe/refund cần phê duyệt riêng.

Nếu lỗi: dừng kích hoạt mới,giữ schema/ledger/dữ liệu phát sinh,rollback code/config được duyệt.
Tắt membership chỉ dừng ưu đãi mới; snapshot/refund history vẫn cần code đọc tương thích.
Lifecycle không được tắt rồi bật tùy ý khi đang có phiên mở: đối soát trước,giữ trạng thái vật lý/quyền.
Không reverse0022–24,restore đè hoặc xóa dữ liệu thật để rollback. Restore backup production là thao tác phục hồi riêng cần phê duyệt.
Rollback code về main cũ sẽ phục hồi hành vi GPS cũ nếu config lịch sử còn đó; phải thông báo đúng thay đổi chính sách.

## Những phê duyệt/quyền còn thiếu

- Quyền đọc Render Dashboard/API/Shell để xác minh actual config/deployment/native; chưa đủ dữ liệu để đánh dấu gate nàyPASS.
- Merge release vào main và deploy,bao gồm thay đổi FACE_ONLY; hiện chưa được cho phép.
- Mọi thay đổi Auto-Deploy/env/native/runtime cần thiết; không tự nâng gói trả phí.
- Migration0022/23/24; sau đó bật từng flag/quyền MANAGER theo review riêng.
- Scheduler/catch-up14cọc hết hạn và mọi tác động provider/ghi nghiệp vụ QA production.
- Camera/iPhone thật và quan sát tải production sau deploy; CI512 không thay nghiệm thu này.

Không có phê duyệt nào được suy ra từ việc CI PASS. Release PR vẫn Draft và production giữ nguyên.
