# Audit trước khi hoàn thiện — 14/10/2026

Baseline: Django/PostgreSQL hiện hữu, 371 tests, migration 0016; model/artifact AI được giữ. Danh sách nguồn: `project-audit-files.txt`. Audit dưới đây dựa trên URL, services, models, templates, static và báo cáo trước; chưa thay cho kết quả live E2E.

| Feature | Status | Missing / broken | UI issue | Action |
|---|---|---|---|---|
| Register/login/logout/profile | Có backend và tests | Chưa audit live | Form chưa đồng bộ | Redesign shared forms, kiểm ownership |
| Home/menu/category/search | Có | Chưa có price range/sort rõ | Banner/cards/navigation cũ | Design system, bộ lọc DB |
| Detail/topping/combo/cart/preorder | Có services | Cần kiểm live các tùy chọn | Action và summary chưa nhất quán | Giữ services, redesign component |
| Booking/table/area | Có locking/service | AI thiếu slot-fill ngày và số đơn lẻ | Form mặc định | Fix parser/memory, giữ reservation service |
| Order/kitchen/invoice/payment/history/review | Có backend và tests | Chưa chứng minh browser vòng đời | Table/action thô | Shared table/form UX + E2E DB riêng |
| Human support chat/WebSocket | Có | Topbar vẫn nói chưa triển khai | Entry point lỗi thời | Nối đúng URL, giữ Channels |
| Management dashboard | Có dữ liệu DB cơ bản | Thiếu một số vận hành/tổng hợp | Small typography, layout cũ | Dashboard DB, visual redesign |
| Menu/category/topping/combo/promotion/voucher/review moderation | Có | Cần kiểm link/action | Table/form chưa đồng bộ | Reusable table controls, action UX |
| Ingredient/recipe/supplier/stock/low stock | Có | Không cần module trùng | Scrolling/action/forms | Shared design, kiểm mutation/CSRF |
| Employee/position/shift/schedule/attendance/payroll | Có | Attendance mới chưa có geofence | Luồng camera chưa rõ | Tích hợp policy vào service, stepper |
| Reports | Có service | Cần mở rộng booking/category/review | Charts/tables thiếu hierarchy | Dữ liệu DB + cards/charts |
| GA/content/collaborative/hybrid/forecast/inventory AI | Có artifact/evaluation | Metrics chủ yếu synthetic; không rewrite | AI dashboard thô | Redesign, giữ model/metric |
| FaceID enrollment | Có ONNX/quality service | 0 enrollment thật, chưa calibration | Thu/lưu chung; thiếu stages | Dedicated page, quality/progress/save |
| FaceID test | Thiếu trang test độc lập | Test hiện dẫn tới attendance | Chưa có result card | Verification-only, không tạo Attendance |
| FaceID attendance | Có service wrapper | Thiếu GPS/policy | Thiếu steps/location/result | GPS → face → existing punch |
| Restaurant location/Leaflet/geofence | Chỉ có lat/lng RestaurantInfo | Thiếu radius/accuracy/policy/event | Chưa có map | Models/migration/service/map settings |
| AI chatbot | Có router/RAG/tools/history | Teencode, budget, date, bare slots, ordinal references lỗi | Log text, thiếu mini chat | Normalize/parser/memory/tool fixes + bubbles |
| Chatbot management | Thiếu | Chưa có fallback thống kê live | Chưa có quản trị | Aggregate dashboard, không lộ history khách |
| 403/404/500/toast/loading/confirm | Không thống nhất | Chưa có shared UX | Default/error/alert | Shared UI components/error templates |
| Navigation/RBAC/link/static | Có role gates | Placeholder topbar và category nav | Thiếu breadcrumb/quick action | Đồng bộ URL; audit browser |
| Live browser/webcam/GPS | Chưa chứng minh | Chrome ERR_ABORTED ở lần trước | N/A | Thử live server; tách real/mock evidence |

Ưu tiên: shared redesign/navigation → chatbot → Face UX → GIS/attendance → live E2E/security → regression/report. Không xóa dữ liệu/migration/tests; không giả enrollment, GPS hay webcam thật.
