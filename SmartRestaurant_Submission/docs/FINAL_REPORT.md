# Smart Restaurant — báo cáo hoàn thiện UI, chatbot, FaceID và GIS

Ngày kiểm chứng: 14/10/2026. Tiếp tục Django/PostgreSQL hiện hữu; không thay stack, không xóa tests, không huấn luyện lại các model AI. Báo cáo này bổ sung cho [AI_REPORT.md](AI_REPORT.md), không thay thế kết quả nghiên cứu cũ.

Cập nhật FaceID/Employee/GPS mới hơn: [FACEID_OPERATIONAL_REPORT.md](FACEID_OPERATIONAL_REPORT.md). Các trạng thái FaceID/calibration và số bản ghi bên dưới là snapshot của giai đoạn UI trước. Pipeline vận hành hiện hỗ trợ recognition nhìn thẳng, threshold PROVISIONAL khi chưa calibrate, liveness tùy settings và HUD không có mini map. DB hiện có 1 profile/15 mẫu từ trước task mới; không suy ra đã kiểm chứng webcam thật.

## A. Feature gap ban đầu

Xem [audit ban đầu](FINAL_FEATURE_AUDIT.md). Backend nghiệp vụ đã có; thiếu thiết kế đồng bộ, bộ lọc giá, chatbot tiếng Việt/multi-turn chắc chắn, trang FaceID test độc lập, UX enrollment và policy GPS phía server. Entry point human chat còn placeholder. Lần kiểm tra browser trước chưa chứng minh live UI.

## B. Feature bổ sung

Design system chung; navigation/breadcrumb/identity theo vai trò; dashboard lấy dữ liệu DB; bộ lọc menu giá/sort/rating; quantity và validation giỏ hàng; assistant đầy đủ và mini; history riêng theo chủ sở hữu; quản trị chatbot dạng tổng hợp; enrollment/test/chấm công theo bước; cấu hình tọa độ/bán kính/accuracy/mode; Leaflet và server Haversine; trang lỗi và UX loading/toast/confirmation.

## C. UI trước/sau

Ảnh trước có sẵn: [admin](../evidence/ARCHIVE_NOTICE.md), [customer](../evidence/ARCHIVE_NOTICE.md). Đây là ảnh lịch sử, không phải ảnh cùng fixture/thời điểm với E2E mới.

Ảnh sau từ Edge live HTTP, dữ liệu QA: [admin desktop](../evidence/ARCHIVE_NOTICE.md), [admin mobile](../evidence/ARCHIVE_NOTICE.md), [menu desktop](../evidence/ARCHIVE_NOTICE.md), [menu mobile](../evidence/ARCHIVE_NOTICE.md), [assistant mobile](../evidence/ARCHIVE_NOTICE.md), [GIS](../evidence/ARCHIVE_NOTICE.md), [attendance](../evidence/ARCHIVE_NOTICE.md).

## D. Admin redesign

Màu xanh rừng/vàng, typography và spacing thống nhất, sidebar theo nhóm, topbar đúng tài khoản/vai trò, cards vận hành, forms/tables/buttons/statuses. Bảng hỗ trợ tìm kiếm/sort/phân trang phía client khi phù hợp. Điều hướng menu/category, inventory, HR, AI, chatbot và location nối URL hiện hữu. Báo cáo và AI được áp dụng shared design; số liệu dashboard/top món dựa DB, không dùng giá catalog giả làm doanh thu.

## E. Customer redesign

Home bổ sung combo/promotion/thông tin nhà hàng/review từ DB. Menu có category/search/min-max price/sort; card hiển thị rating thực. Detail có nguyên liệu và quantity. Cart kiểm tra topping trước khi thay đổi dữ liệu; quantity giới hạn 1–99. Booking/history/invoice/account dùng nền thiết kế chung. Assistant có bubble, thời gian, typing, suggestions, Enter/Shift+Enter và mini panel.

## F. FaceID flow

OpenCV xử lý ảnh, FaceNet ONNX qua ONNX Runtime CPU tạo embedding; MediaPipe landmark hỗ trợ quality và liveness cơ bản. Không dùng facenet-pytorch. Model/version/hash và cache giữ tại `ai_models/pretrained/manifest.json`; không tải lại hoặc downgrade stack AI.

## G. Face enrollment flow

Quản lý mở trang riêng của nhân viên → chủ động bật camera → thu mẫu trước/trái/phải/trước → xem quality/progress → lưu rõ ràng hoặc hủy. Thu 15 mẫu theo giai đoạn; backend xác thực chất lượng/identity. Raw frame trong browser được bỏ khi kết thúc; camera dừng khi hủy/rời trang. Có ngày, số mẫu, trạng thái và hành động quản lý profile. Không tự tạo enrollment giả.

## H. Attendance flow

Nhân viên chọn ca và vào/ra → kiểm tra vị trí nếu policy yêu cầu → challenge/FaceID nếu policy yêu cầu → existing personnel punch service. Các mode: FACE_AND_GPS, FACE_ONLY, GPS_ONLY. Endpoint self-service cũ không còn đường bỏ qua policy. Manager vẫn có nghiệp vụ HR sửa chấm công theo quyền hiện hữu. Trang test FaceID chỉ verify, không tạo Attendance.

## I. GPS/Haversine architecture

RestaurantInfo giữ tọa độ nhà hàng; AttendanceLocationPolicy giữ radius, max accuracy, mode và active. Browser gửi lat/lng/accuracy; server kiểm tra finite/bounds, tự tính Haversine với R=6.371.008,8 m, so radius và accuracy. Bỏ qua distance/inside/verified do client gửi. Thiếu policy/toạ độ cần thiết sẽ từ chối. Preview không ghi event; attendance attempt ghi event và snapshot policy. Identity, attendance và audit thành công được xử lý với transaction; challenge thất bại vẫn bị tiêu thụ để ngăn replay.

Leaflet 1.9.4 được cache local, kèm license/hash tại `static/vendor/leaflet/manifest.json`; nguồn [Leaflet download](https://leafletjs.com/download.html). Tiles OpenStreetMap cần mạng. Map hiển thị marker, radius, vị trí nhân viên và vòng accuracy; cấu hình manager hỗ trợ kéo marker.

## J. Chatbot root cause

Router cũ nhầm từ “đơn” trong “hóa đơn”; teencode và dấu tiếng Việt thiếu chuẩn hóa; giá k/tr/dấu phẩy và khoảng tiền thiếu xử lý; ngày dạng 18/10, số khách trả lời đơn lẻ và giờ mơ hồ chưa giữ slot tốt; tham chiếu món số thứ tự thiếu state. UI cũ hiển thị log và không có history riêng rõ ràng.

## K. Chatbot fixes

Chuẩn hóa alias bảo thủ, giữ đơn vị tiền trước alias; parser ngân sách/khoảng giá/ngày/giờ; ưu tiên invoice intent; hỏi slot còn thiếu và làm rõ 7h; lưu menu IDs/selected item; gọi shared cart service. Search/recommendation lọc món hợp lệ bằng DB, sử dụng cold-start hiện hữu khi xếp hạng không còn món hợp lệ. Trả giá/availability hiện tại; không đoán dữ liệu không có. RAG giữ sentence-transformers/FAISS/BM25 CPU. History GET giới hạn 30 tin, owner/session scoped, no-store; trang manager chỉ tổng hợp, không lộ hội thoại khách.

## L. Examples trước/sau

| Câu/tình huống | Lỗi ban đầu | Hành vi sau |
|---|---|---|
| “hóa đơn của tôi” | Có thể vào order intent | Payment/invoice của chủ sở hữu |
| “món từ 300 đến 700k” | Thiếu unit của cận dưới | DB filter 300.000–700.000 |
| “1tr2”, “1,5tr” | Parser hạn chế | 1.200.000 / 1.500.000 |
| Booking → “6” → “18/10” → “7h” → “tối” | Mất/không điền slot | Giữ 6 khách/ngày, làm rõ giờ rồi chọn 19h |
| Menu → “món thứ 2” → “thêm 2 phần” | Thiếu tham chiếu | Chọn ID kết quả thứ 2 rồi shared cart add |
| Câu ngoài dữ liệu hỗ trợ | Có nguy cơ trả lời sai | Fallback rõ ràng |

Đây là các hành vi được kiểm tra trong corpus tác giả tự xây dựng; không đại diện mọi cách diễn đạt tiếng Việt.

## M. Models changed

Thêm AttendanceLocationPolicy (one-to-one RestaurantInfo) và AttendanceLocationEvent (employee, attendance nullable, action, coordinates, accuracy, distance, status, policy snapshot, timestamp). Không đổi model dự báo/recommendation/FaceNet weights. Metadata quality face bổ sung kích thước và số mặt.

## N. Migrations

`customers/migrations/0017_attendancelocationevent_attendancelocationpolicy.py`: tạo hai bảng và constraints. Migrate PASS; makemigrations --check PASS. Không tự điền tọa độ hoặc policy vào DB chính.

## O. Services

Mới: location_service. Cập nhật: chatbot normalization/router/memory/tools/answer guard, face_enrollment_service verify_identity dùng chung, menu_service rating/order, forecast_service cache model theo artifact path. Personnel punch, booking, cart, order, payment và AI algorithms tiếp tục được tái sử dụng.

## P. Views

location_views: settings, preview, secure attendance. final_views: enrollment/test verification-only/chatbot management. ai_phase_views: history và attendance integration. Customer views: menu filter/detail/home/cart validation. Context processor cung cấp navigation và dashboard DB.

## Q. URLs

Các entry chính: `/management/settings/location/`, `/work/location/check/`, `/work/attendance/verify/`, `/work/faceid/`, `/management/ai/faces/<pk>/enrollment/`, `/management/ai/faces/test/`, `/management/ai/chatbot/`, `/ai/chat/`, `/ai/chat/history/`. Giữ URL nghiệp vụ cũ và điều chỉnh entry point cần bảo vệ.

## R. Templates

Shared base/admin/customer; menu_filters, dish/detail/home; chat/chat_surface; faces_table/enrollment/face_test/face_attendance; location settings; AI metrics/provenance; lỗi 403/404/500. Xem source census để có danh sách chính xác toàn nguồn.

## S. CSS/JS

`static/ui/design-system.css`, `product.js`, `dashboard.js`, `reports.js`, favicon; `static/ai/assistant.css`, `assistant.js`, `face-flow.js`; `static/location/maps.js`; chỉnh admin main.js/navigation. Leaflet được cache local. Browser audit phát hiện duplicate const avatar và đã sửa. Lần live cuối không ghi nhận Runtime.exceptionThrown; raw field console_errors giữ 4 Network.loadingFailed có canceled=true/ERR_ABORTED khi điều hướng. Đây là request bị browser hủy, không phải bằng chứng exception JavaScript; không xóa chúng khỏi evidence.

## T. Tests added

23 tests trong `customers/test_final_phase.py`: normalization/money/time/date, booking slots, ordinal/cart, DB menu filters, quantity/topping, Haversine/bounds/dateline/accuracy, policy fail-closed, secure attendance, không tin client flags, không mutate khi từ chối, legacy bypass, RBAC/CSRF/history privacy. Live E2E riêng bổ sung HTTP, WebSocket, browser và corpus chatbot.

## U. Old tests retained

Giữ baseline 371 tests. Một regression ordering menu do annotation rating được phát hiện và sửa bằng explicit PK ordering; không xóa test để đạt PASS.

## V. Total PASS

| Kiểm tra | Kết quả |
|---|---|
| Django check | PASS |
| makemigrations --check | PASS |
| migrate --noinput | PASS |
| Full regression phiên bản cuối | 394/394 PASS, 214,256 giây test runner |
| AI + final targeted sau chỉnh sửa cuối | 63/63 PASS |
| pip check | PASS |
| AST/templates/named URLs/static/catalog images | 286 file nguồn, không có lỗi trong source audit |

Logs: [ai_verification](../evidence/ARCHIVE_NOTICE.md), [full test log](../evidence/ARCHIVE_NOTICE.md), [source audit](../evidence/ARCHIVE_NOTICE.md). 51 tests module07/operational seed cũng PASS khi thêm báo cáo. Không cài lại/downgrade các package AI người dùng đã chuẩn bị. Redis chỉ là tùy chọn production, chưa cài bắt buộc.

## W. Live browser result

Edge headless truy cập server HTTP thật và PostgreSQL QA riêng. 34 manager routes/15 customer routes trả 200; kiểm tra cart/booking/voucher/order → kitchen → invoice/payment demo/review/human chat/register/login và WebSocket chat.updated. Browser trực tiếp thao tác assistant bubbles, menu filter/cart và GPS_ONLY attendance. Không phải mọi CRUD/action đều đã được click thủ công.

DB QA được xóa trong finally; DB chính không seed fixture. Snapshot chính: Order 1, OrderItem 5, MenuItem 45, Employee 5, Ingredient 71, FaceProfile 0, FaceEmbedding 0, LocationPolicy 0. [Evidence JSON](../evidence/ARCHIVE_NOTICE.md), [server log](../evidence/ARCHIVE_NOTICE.md).

## X. Mobile result

Menu ở 1920×1080, 1366×768, 768×1024, 390×844; thêm 14 trang manager/customer/staff ở 1366/768/390 (42 checks). Không phát hiện horizontal overflow trong các viewport đã kiểm tra. Screenshot là live browser, không phải render template tĩnh. Chưa chứng minh mọi trình duyệt/thiết bị.

## Y. Webcam status

**Chưa kiểm tra webcam thật.** UI, endpoints, quality/liveness services và tests có; chưa có bằng chứng camera permission/ánh sáng/góc mặt trên máy người dùng.

## Z. GPS status

**Chỉ AUTOMATED MOCK qua DevTools và request QA.** Haversine/server policy đã kiểm tra; chưa kiểm tra sensor GPS thật, accuracy trong nhà hoặc chống giả mạo vị trí thiết bị. GPS browser không phải cơ chế chống spoofing tuyệt đối.

## AA. FaceID real enrollment status

**0 profile và 0 embedding thật trên DB chính.** Không tạo fake enrollment hay gọi mock là nhận diện thành công thật.

## AB. Threshold calibration status

**Chưa calibrate threshold bằng genuine/impostor thật.** Không có FAR/FRR/EER thực tế. Phải thu tập có consent và kiểm tra môi trường vận hành trước khi sử dụng chấm công thật.

## AC. Synthetic/proxy metrics

Corpus độc lập do tác giả viết: 185 queries, 7 conversations, DB fixture QA mô phỏng. Intent/tool/price entity/context slot assertions đạt 1,0; 25 grounding assertions đạt 1,0; HTTP errors 0; fallback 5/185 = 2,70%, incorrect fallback 0. Đây là acceptance assertion proxies, **không phải accuracy ngữ nghĩa từ người dùng thật**. Các nhóm không có assertion đầy đủ không được suy ra đúng toàn bộ câu trả lời.

Forecast/recommendation/GA metrics cũ giữ provenance trong AI_REPORT và UI. Revenue MAPE cũ 417,371531% vẫn giữ; không tuyên bố forecast đã đủ chính xác cho vận hành. Không thay metric bằng số đẹp hơn.

## AD. Limitations

Chưa có webcam/GPS/enrollment/calibration thật; liveness cơ bản không tương đương anti-spoof chuyên dụng. OSM tiles cần mạng. InMemory Channels phù hợp local một process; multi-process cần Redis cấu hình. QR/payment QA là demo, không xác minh giao dịch ngân hàng thật. Bảng search/sort client chỉ xử lý dữ liệu trang đã tải. Reports có bar charts cho dữ liệu numeric cùng bảng; danh mục dùng doanh số dòng món trước giảm giá, phương thức dùng thực thu, không cộng lẫn đại lượng này. Source audit và các route đã kiểm tra không chứng minh mọi đường dẫn động hoặc mọi điều kiện dữ liệu đều không lỗi.

## AE. Manual steps user must still perform

Lưu vị trí thật và policy tại settings; tạo/kiểm tra ca nhân viên; enroll người thật có consent; kiểm tra test-only; calibrate threshold; test GPS thật và accuracy; test attendance đủ ba mode và in/out; xem audit/Attendance; review chatbot với câu thực và chấm tay; kiểm tra thanh toán/Redis khi triển khai production. Không cần thay stack AI đã cài.

## AF. Demo instructions

Xem [FINAL_DEMO.md](FINAL_DEMO.md). Có thể demo UI/nghiệp vụ/chatbot ngay với tài khoản và dữ liệu hợp lệ; phần webcam/GPS thật chỉ được trình bày là đã đạt sau khi hoàn thành bước thủ công. Trạng thái: phần mềm và kiểm chứng tự động đã hoàn thiện đáng kể; không tuyên bố hệ thống đạt 100% thực địa.
