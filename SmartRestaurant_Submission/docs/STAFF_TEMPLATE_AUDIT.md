# Audit templates và quyết định UI

Đã đọc 153 templates. Phân loại dựa nguồn/layout; không thay cho live QA từng route.

| Template | Base | Quyết định | Action |
|---|---|---|---|
| `403.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `404.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `500.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/ai/chatbot.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/chatbot_management.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/dashboard.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/demand-forecast.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/employee_link.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/enrollment.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/face_test.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/faces.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/faces_table.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/forecast.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/inventory-ai.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/inventory.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/metrics_cards.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/nav.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/operational_faces.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/provenance.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/recommendations.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/revenue-forecast.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/schedules.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/ai/straight_test.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/base.html` | `"index.html"` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/business/_invoice_content.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/_kitchen_content.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/_order_content.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/_payments_content.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/_receipt_content.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/entry.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/invoice.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/kitchen.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/list.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/order.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/payments.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/receipt.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/business/stock.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/communication/messages.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/customers/booking-history.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/customers/customers.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/customers/feedback.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/customers/order-history.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/employees/ai-schedule.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/employees/attendance.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/employees/employees.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/employees/payroll.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/employees/shifts.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/gis/attendance-map.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/header.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/inventory/ingredients.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/inventory/recipes.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/inventory/stock-alerts.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/inventory/suppliers.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/inventory/transactions.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/location/settings.html` | `'index.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `admin/module07/chat.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/module07/form.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/module07/payroll.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/module07/reports.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/reports/employees.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/reports/foods.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/reports/inventory.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/reports/orders.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/reports/revenue.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `admin/restaurant/_booking-order.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/_messages.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/_pagination.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/areas.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/booking-detail.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/bookings.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/categories.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/combos.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/kitchen.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/menu-form.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/menu.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/orders.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/payments.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/promotions.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/resource-form.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/reviews.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/tables.html` | `management_base` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/restaurant/toppings.html` | `partial/standalone` | Giữ cấu trúc, đồng bộ staff/admin | Base theo vai trò; shared card/table/form polish |
| `admin/sidebar.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/system/account-edit.html` | `"index.html"` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/system/accounts.html` | `"index.html"` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/system/activity-logs.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `admin/system/settings.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/_dish.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/_invoice_content.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/about.html` | `"customer/base.html"` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/account/change-password.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/account/edit-profile.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/account/favorites.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/account/profile.html` | `"customer/base.html"` | Nâng cấp trong task staff | Shared components/layout mới |
| `customer/account/reviews.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/account/staff-home.html` | `"customer/base.html"` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/ai/chat.html` | `'customer/base.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `customer/ai/chat_surface.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `customer/ai/face_attendance.html` | `personal_base` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `customer/ai/realtime_attendance.html` | `partial/standalone` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `customer/ai/recommendations.html` | `'customer/base.html'` | Giữ UI đã hoàn thiện | Giữ FaceID/GPS/AI logic; staff attendance đổi shell |
| `customer/auth/forgot-password.html` | `partial/standalone` | Giữ bố cục đã có | Footer/flex shell/form accent; không rewrite |
| `customer/auth/login.html` | `"customer/base.html"` | Giữ bố cục đã có | Footer/flex shell/form accent; không rewrite |
| `customer/auth/register.html` | `"customer/base.html"` | Giữ bố cục đã có | Footer/flex shell/form accent; không rewrite |
| `customer/base.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/booking-success.html` | `partial/standalone` | Giữ bố cục đã có | Footer/flex shell/form accent; không rewrite |
| `customer/booking.html` | `"customer/base.html"` | Giữ bố cục đã có | Footer/flex shell/form accent; không rewrite |
| `customer/cart.html` | `"customer/base.html"` | Giữ bố cục đã có | Footer/flex shell/form accent; không rewrite |
| `customer/chatbot.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/checkout.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/contact.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/food-detail.html` | `"customer/base.html"` | Giữ bố cục đã có | Footer/flex shell/form accent; không rewrite |
| `customer/footer.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `customer/header.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/home.html` | `"customer/base.html"` | Giữ bố cục đã có | Footer/flex shell/form accent; không rewrite |
| `customer/invoice.html` | `"customer/base.html"` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/invoices.html` | `"customer/base.html"` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/menu.html` | `"customer/base.html"` | Giữ bố cục đã có | Footer/flex shell/form accent; không rewrite |
| `customer/menu_filters.html` | `partial/standalone` | Giữ bố cục đã có | Footer/flex shell/form accent; không rewrite |
| `customer/module07/about.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/module07/cart_extras.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/module07/chat.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/module07/combos.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/module07/history.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/module07/history_detail.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/module07/my_work.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/module07/payroll.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/module07/promotions.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/module07/reviews.html` | `'customer/base.html'` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/orders/order-detail.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `customer/orders/order-tracking.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `customer/orders/orders.html` | `partial/standalone` | Legacy/prototype cần phân biệt với route hiện hành | Không xóa; route hiện hành dùng generic/shared templates. Chưa khẳng định mọi prototype có live route. |
| `customer/payment-result.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `customer/portal_footer.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `customer/recommendations.html` | `"customer/base.html"` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `index.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `shared/module07/chat_app.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `shared/module07/chat_content.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `shared/module07/chat_messages.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `shared/module07/item_extras.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `shared/module07/payroll_content.html` | `partial/standalone` | Shared/partial hoặc giữ theo design system | Kiểm tra nguồn; browser QA theo route ưu tiên |
| `staff/base.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/chat.html` | `'staff/base.html'` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/dashboard.html` | `'staff/base.html'` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/empty.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/icons.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/kitchen_board.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/management.html` | `'staff/base.html'` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/payroll.html` | `'staff/base.html'` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/payroll_stats.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/profile.html` | `'staff/base.html'` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/shift_card.html` | `partial/standalone` | Nâng cấp trong task staff | Shared components/layout mới |
| `staff/work.html` | `'staff/base.html'` | Nâng cấp trong task staff | Shared components/layout mới |
