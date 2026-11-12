# Ma trận route/service/model/permission/test

Kiểm kê tĩnh, không tự coi có test tham chiếu là runtime PASS.

| Route | View | Service/model trực tiếp | Permission decorator | Test reference | Trạng thái |
| --- | --- | --- | --- | --- | --- |
| management/orders/<int:pk>/release-table/ | customers.table_session_views.release_order_table |  | require_POST, capability_required('customers.change_order') |  | CODE/REFERENCE; chưa E2E từng route |
| management/table-assignments/ | customers.table_assignment_views.assignments | RestaurantTable, TableServiceAssignment | login_required | test_service_assignment_flow.py | CODE/REFERENCE; chưa E2E từng route |
| robots.txt | customers.seo.robots |  | require_safe |  | CODE/REFERENCE; chưa E2E từng route |
| sitemap.xml | django.contrib.sitemaps.views.sitemap |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| healthz/ | restaurant_system.health.health |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| booking/<int:pk>/deposit/ | customers.deposit_views.deposit_page | service, BookingDeposit | login_required, require_GET | tests.py, test_booking_flow.py, test_deposit.py, test_module02.py | CODE/REFERENCE; chưa E2E từng route |
| booking/<int:pk>/deposit/checkout/ | customers.deposit_views.checkout_start | service | login_required, require_POST | test_deposit.py | CODE/REFERENCE; chưa E2E từng route |
| booking/<int:pk>/deposit/success/ | customers.deposit_views.deposit_page | service, BookingDeposit | login_required, require_GET | test_deposit.py | CODE/REFERENCE; chưa E2E từng route |
| booking/<int:pk>/deposit/status/ | customers.deposit_views.deposit_status | service, BookingDeposit | login_required, require_GET | test_deposit.py | CODE/REFERENCE; chưa E2E từng route |
| stripe/webhook/ | customers.deposit_views.stripe_webhook | service | csrf_exempt, require_POST | test_deposit.py | CODE/REFERENCE; chưa E2E từng route |
| management/booking-deposits/ | customers.deposit_views.management_deposits | BookingDeposit | capability_required('customers.view_bookingdeposit') |  | CODE/REFERENCE; chưa E2E từng route |
| management/purchase-orders/ | customers.operations_views.purchase_orders | Purchaseservice_scope | capability_required('customers.view_purchaseorder') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| management/purchase-orders/add/ | customers.operations_views.purchase_add |  | capability_required('customers.add_purchaseorder') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| management/purchase-orders/<int:pk>/ | customers.operations_views.purchase_detail | Purchaseservice_scope | capability_required('customers.view_purchaseorder') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| management/purchase-orders/<int:pk>/action/ | customers.operations_views.purchase_action | PurchaseOrderItem | require_POST, capability_required('customers.view_purchaseorder') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| management/supplier-prices/ | customers.operations_views.prices | StockReceiptItem | capability_required('customers.view_stockreceipt') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| management/food-cost/ | customers.operations_views.food_cost | Category | capability_required('customers.view_recipeingredient') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| management/audit-log/ | customers.operations_views.audit_logs | AuditLog | require_GET, capability_required('customers.view_auditlog') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| management/loyalty/ | customers.operations_views.loyalty_management | service_scope, CustomerLoyalty | capability_required('customers.view_customerloyalty') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| management/loyalty/<int:pk>/adjust/ | customers.operations_views.loyalty_adjust |  | require_POST, capability_required('customers.adjust_customerloyalty') |  | CODE/REFERENCE; chưa E2E từng route |
| membership/ | customers.operations_views.loyalty_customer | CustomerLoyalty, LoyaltyTransaction | login_required | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| booking/waitlist/ | customers.operations_views.waitlist_customer | advanced, BookingWaitlist | login_required |  | CODE/REFERENCE; chưa E2E từng route |
| management/waitlist/ | customers.operations_views.waitlist_management | BookingWaitlist | capability_required('customers.view_bookingwaitlist') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| booking/waitlist/<int:pk>/action/ | customers.operations_views.waitlist_action | advanced | require_POST, login_required |  | CODE/REFERENCE; chưa E2E từng route |
| management/bookings/<int:pk>/operations/ | customers.operations_views.booking_operations | advanced, service_scope | capability_required('customers.view_booking') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/<int:pk>/transfer/ | customers.operations_views.order_transfer | advanced, service_scope | capability_required('customers.transfer_table') |  | CODE/REFERENCE; chưa E2E từng route |
| management/tables/<int:pk>/history/ | customers.operations_views.table_history | service_scope, AuditLog | capability_required('customers.view_restauranttable') | test_operations.py | CODE/REFERENCE; chưa E2E từng route |
| booking/availability/ | customers.booking_workspace.availability |  | login_required | test_grouped_workspace.py, test_table_time_selection.py | CODE/REFERENCE; chưa E2E từng route |
| management/ai/faces/accounts/<int:user_id>/ | customers.employee_identity_views.employee_link | Employee | role_required('ADMIN', 'MANAGER'), capability_required('customers.change_employee') | test_face_operational.py | CODE/REFERENCE; chưa E2E từng route |
| work/faceid/test/ | customers.final_views.self_test_face | FaceAudit | face_api, role_required('STAFF', 'MANAGER', 'ADMIN'), require_POST | test_face_operational.py | CODE/REFERENCE; chưa E2E từng route |
| work/faceid/quality/ | customers.ai_phase_views.face_quality |  | face_api, role_required('ADMIN', 'MANAGER', 'STAFF'), require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| favicon.ico | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| management/ai/chatbot/ | customers.final_views.chatbot_management | AIMessage | role_required('ADMIN', 'MANAGER') | test_final_phase.py | CODE/REFERENCE; chưa E2E từng route |
| management/ai/faces/<int:pk>/enrollment/ | customers.final_views.enrollment_page |  | role_required('ADMIN', 'MANAGER'), capability_required('customers.change_employee') | test_face_ui_vi.py | CODE/REFERENCE; chưa E2E từng route |
| management/ai/faces/test/ | customers.final_views.test_page |  | role_required('ADMIN', 'MANAGER'), capability_required('customers.change_employee') | test_face_ui_vi.py, test_final_phase.py | CODE/REFERENCE; chưa E2E từng route |
| management/ai/faces/test/verify/ | customers.final_views.test_face | FaceAudit | face_api, role_required('ADMIN', 'MANAGER'), capability_required('customers.change_employee'), require_POST | test_face_operational.py | CODE/REFERENCE; chưa E2E từng route |
| management/settings/location/ | customers.location_views.settings_page | AttendanceLocationPolicy, RestaurantInfo | role_required('ADMIN'), capability_required('customers.change_restaurantinfo') | test_face_attendance_integration.py, test_final_phase.py, test_location_admin_policy.py | CODE/REFERENCE; chưa E2E từng route |
| work/location/check/ | customers.location_views.check_location |  | face_api, role_required('STAFF', 'MANAGER', 'ADMIN'), require_POST | test_final_phase.py | CODE/REFERENCE; chưa E2E từng route |
| work/attendance/status/ | customers.location_views.attendance_status |  | face_api, role_required('STAFF', 'MANAGER', 'ADMIN'), require_GET | test_face_attendance_integration.py, test_face_gps_readiness.py | CODE/REFERENCE; chưa E2E từng route |
| work/attendance/verify/ | customers.location_views.attendance |  | face_api, role_required('STAFF', 'MANAGER', 'ADMIN'), require_POST | test_face_attendance_integration.py, test_final_phase.py | CODE/REFERENCE; chưa E2E từng route |
| management/ai/ | customers.ai_phase_views.dashboard | Employee, FaceAudit, FaceEmbedding, FaceProfile | role_required('ADMIN', 'MANAGER') | test_ai_phase.py | CODE/REFERENCE; chưa E2E từng route |
| management/ai/forecast/ | customers.ai_phase_views.forecast |  | role_required('ADMIN', 'MANAGER') |  | CODE/REFERENCE; chưa E2E từng route |
| management/ai/inventory/ | customers.ai_phase_views.inventory | Supplier | role_required('ADMIN', 'MANAGER') |  | CODE/REFERENCE; chưa E2E từng route |
| management/ai/inventory/policy/ | customers.ai_phase_views.supply_policy | IngredientSupplyPolicy | role_required('ADMIN', 'MANAGER'), require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| management/ai/faces/ | customers.ai_phase_views.faces | FaceAudit | role_required('ADMIN', 'MANAGER') | test_face_operational.py, test_face_ui_vi.py, test_final_phase.py | CODE/REFERENCE; chưa E2E từng route |
| management/ai/faces/quality/ | customers.ai_phase_views.face_quality |  | face_api, role_required('ADMIN', 'MANAGER', 'STAFF'), require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| management/ai/faces/<int:pk>/enroll/ | customers.ai_phase_views.enrollment |  | face_api, role_required('ADMIN', 'MANAGER'), require_POST | test_ai_phase.py, test_face_attendance_integration.py, test_face_operational.py | CODE/REFERENCE; chưa E2E từng route |
| management/ai/faces/<int:pk>/delete/ | customers.ai_phase_views.face_delete | FaceProfile | role_required('ADMIN', 'MANAGER'), require_POST | test_ai_phase.py | CODE/REFERENCE; chưa E2E từng route |
| work/faceid/ | customers.ai_phase_views.face_attendance |  | role_required('STAFF', 'ADMIN', 'MANAGER') | test_face_gps_readiness.py, test_face_ui_vi.py, test_staff_portal.py | CODE/REFERENCE; chưa E2E từng route |
| work/faceid/challenge/ | customers.ai_phase_views.challenge |  | face_api, role_required('STAFF', 'ADMIN', 'MANAGER'), require_POST | test_face_attendance_integration.py | CODE/REFERENCE; chưa E2E từng route |
| work/faceid/verify/ | customers.ai_phase_views.verify |  | face_api, role_required('STAFF', 'ADMIN', 'MANAGER'), require_POST | test_final_phase.py | CODE/REFERENCE; chưa E2E từng route |
| ai/chat/ | customers.ai_phase_views.chat_page |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| ai/chat/message/ | customers.ai_phase_views.chat_message | AIConversation, AIMessage | require_POST | test_ai_phase.py, test_final_phase.py | CODE/REFERENCE; chưa E2E từng route |
| ai/chat/history/ | customers.ai_phase_views.chat_history | AIConversation | require_GET | test_final_phase.py | CODE/REFERENCE; chưa E2E từng route |
| management/schedules/ai/ | customers.ai_views.ai_schedules | Employee, Shift | role_required('ADMIN', 'MANAGER') | test_ai01_ai02.py | CODE/REFERENCE; chưa E2E từng route |
| management/recommendations/ | customers.ai_views.recommendation_demo |  | role_required('ADMIN', 'MANAGER'), capability_required('customers.view_order'), capability_required('customers.view_menuitem') | test_ai01_ai02.py | CODE/REFERENCE; chưa E2E từng route |
| recommendations/ | customers.ai_views.customer_recommendations |  |  | test_ai01_ai02.py | CODE/REFERENCE; chưa E2E từng route |
| management/module07/<str:resource>/ | customers.module07_views.resource_list | model | login_required | test_module07.py | CODE/REFERENCE; chưa E2E từng route |
| management/module07/<str:resource>/add/ | customers.module07_views.resource_edit |  | login_required | test_face_attendance_integration.py, test_module07.py | CODE/REFERENCE; chưa E2E từng route |
| management/module07/<str:resource>/<int:pk>/edit/ | customers.module07_views.resource_edit |  | login_required | test_location_admin_policy.py | CODE/REFERENCE; chưa E2E từng route |
| management/module07/<str:resource>/<int:pk>/state/ | customers.module07_views.resource_state | hr, Combo | login_required, require_POST | test_face_attendance_integration.py | CODE/REFERENCE; chưa E2E từng route |
| management/payroll/ | customers.module07_views.payroll_list | Payroll | capability_required('customers.view_payroll') | test_module07.py, test_staff_portal.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/<int:pk>/combo/ | customers.module07_views.order_combo |  | capability_required('customers.change_order'), capability_required('customers.add_orderitem'), require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| management/payroll/calculate/ | customers.module07_views.payroll_calculate | hr | capability_required('customers.add_payroll'), role_required('ADMIN', 'MANAGER') |  | CODE/REFERENCE; chưa E2E từng route |
| payroll/<int:pk>/ | customers.module07_views.payroll_detail | Payroll | login_required | test_module07.py, test_staff_portal.py | CODE/REFERENCE; chưa E2E từng route |
| management/payroll/<int:pk>/state/ | customers.module07_views.payroll_state | hr | login_required, require_POST, role_required('ADMIN', 'MANAGER') |  | CODE/REFERENCE; chưa E2E từng route |
| management/reports/ | customers.module07_views.reports |  | role_required('ADMIN', 'MANAGER') |  | CODE/REFERENCE; chưa E2E từng route |
| work/ | customers.module07_views.my_work | Attendance, Employee, Payroll, WorkSchedule | role_required('STAFF', 'MANAGER', 'ADMIN') | test_module07.py, test_staff_portal.py | CODE/REFERENCE; chưa E2E từng route |
| work/<int:pk>/punch/ | customers.module07_views.punch |  | login_required, require_POST | test_final_phase.py | CODE/REFERENCE; chưa E2E từng route |
| combos/ | customers.module07_views.combos | Combo |  | test_grouped_workspace.py | CODE/REFERENCE; chưa E2E từng route |
| combos/<int:pk>/cart/ | customers.module07_views.combo_cart |  | require_POST | test_customer_booking_workspace.py, test_module07.py | CODE/REFERENCE; chưa E2E từng route |
| purchases/ | customers.module07_views.history | Order | login_required | test_module07.py | CODE/REFERENCE; chưa E2E từng route |
| purchases/<int:pk>/ | customers.module07_views.history | Order | login_required | test_module07.py | CODE/REFERENCE; chưa E2E từng route |
| purchases/<int:pk>/voucher/ | customers.module07_views.voucher |  | login_required, require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| purchases/<int:pk>/review/ | customers.module07_views.review_create |  | login_required, require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| reviews/ | customers.module07_views.reviews | Review | login_required | test_module07.py | CODE/REFERENCE; chưa E2E từng route |
| reviews/<int:pk>/visibility/ | customers.module07_views.review_visibility | Review | capability_required('customers.change_review'), require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| chat/ | customers.module07_views.chat | Conversation, ConversationParticipant | login_required |  | CODE/REFERENCE; chưa E2E từng route |
| chat/<int:pk>/ | customers.module07_views.chat | Conversation, ConversationParticipant | login_required | test_module07.py, test_staff_portal.py | CODE/REFERENCE; chưa E2E từng route |
| management/kitchen/ | customers.business_views.kitchen_queue | OrderItem | capability_required('customers.view_order'), capability_required('customers.view_orderitem') | test_staff_portal.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/<int:pk>/send-kitchen/ | customers.business_views.order_send_kitchen |  | capability_required('customers.change_order'), capability_required('customers.change_orderitem'), require_POST | test_module04.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/<int:pk>/items/<int:item_id>/kitchen/ | customers.business_views.kitchen_item_status |  | capability_required('customers.change_order'), capability_required('customers.change_orderitem'), require_POST | test_module04.py, test_module06.py | CODE/REFERENCE; chưa E2E từng route |
| management/menu/ | customers.business_views.menu | Category, MenuItem | capability_required('customers.view_menuitem') | test_staff_portal.py | CODE/REFERENCE; chưa E2E từng route |
| management/categories/ | customers.business_views.categories | Category | capability_required('customers.view_category') |  | CODE/REFERENCE; chưa E2E từng route |
| management/suppliers/ | customers.business_views.suppliers | Supplier | capability_required('customers.view_supplier') | test_module06.py | CODE/REFERENCE; chưa E2E từng route |
| management/ingredients/ | customers.business_views.ingredients | Ingredient | capability_required('customers.view_ingredient') | test_module06.py | CODE/REFERENCE; chưa E2E từng route |
| management/recipes/ | customers.business_views.recipes | MenuItem, RecipeIngredient | capability_required('customers.view_recipeingredient') | test_module06.py | CODE/REFERENCE; chưa E2E từng route |
| management/recipes/<int:pk>/delete/ | customers.business_views.recipe_delete |  | capability_required('customers.delete_recipeingredient'), require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| management/stock-alerts/ | customers.business_views.alerts | Ingredient | capability_required('customers.view_ingredient') | test_module06.py | CODE/REFERENCE; chưa E2E từng route |
| management/resources/<str:resource>/add/ | customers.business_views.resource_edit |  |  | test_business.py | CODE/REFERENCE; chưa E2E từng route |
| management/resources/<str:resource>/<int:pk>/edit/ | customers.business_views.resource_edit |  |  | test_module06.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/ | customers.business_views.orders | service_scope | capability_required('customers.view_order') |  | CODE/REFERENCE; chưa E2E từng route |
| management/orders/add/ | customers.business_views.order_add |  | capability_required('customers.add_order') |  | CODE/REFERENCE; chưa E2E từng route |
| management/orders/from-booking/ | customers.business_views.order_bookings | service_scope | capability_required('customers.add_order') | test_table_time_selection.py | CODE/REFERENCE; chưa E2E từng route |
| management/bookings/<int:pk>/open-order/ | customers.business_views.booking_open_order |  | capability_required('customers.add_order'), capability_required('customers.add_orderitem'), require_POST | test_module03.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/<int:pk>/items/add/ | customers.business_views.order_item_add |  | capability_required('customers.change_order'), capability_required('customers.add_orderitem'), require_POST | test_master_service_safety.py, test_module03.py, test_module04.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/<int:pk>/items/<int:item_id>/quantity/ | customers.business_views.order_item_quantity |  | capability_required('customers.change_order'), capability_required('customers.change_orderitem'), require_POST | test_module03.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/<int:pk>/items/<int:item_id>/remove/ | customers.business_views.order_item_remove |  | capability_required('customers.change_order'), capability_required('customers.change_orderitem'), require_POST | test_module03.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/<int:pk>/ | customers.business_views.order_detail | service_scope, Combo | capability_required('customers.view_order') | test_business.py, test_master_service_safety.py, test_module03.py, test_module04.py, test_module06.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/<int:pk>/status/ | customers.business_views.order_status |  | capability_required('customers.change_order'), require_POST | test_business.py, test_module03.py, test_module04.py | CODE/REFERENCE; chưa E2E từng route |
| management/orders/<int:pk>/invoice/ | customers.business_views.invoice_issue |  | capability_required('customers.add_invoice'), require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| management/payments/ | customers.payment_views.management_payments | service_scope | capability_required('customers.view_invoice'), capability_required('customers.view_payment') | test_module05.py | CODE/REFERENCE; chưa E2E từng route |
| management/payments/<int:pk>/receipt/ | customers.payment_views.payment_receipt | service_scope | capability_required('customers.view_invoice'), capability_required('customers.view_payment') | test_module05.py | CODE/REFERENCE; chưa E2E từng route |
| management/invoices/<int:pk>/ | customers.business_views.invoice_detail | service_scope | capability_required('customers.view_invoice') | test_business.py | CODE/REFERENCE; chưa E2E từng route |
| management/invoices/<int:pk>/payments/add/ | customers.business_views.payment_add |  | capability_required('customers.add_payment'), require_POST | test_business.py, test_module05.py | CODE/REFERENCE; chưa E2E từng route |
| management/payments/<int:pk>/confirm/ | customers.business_views.payment_confirm |  | capability_required('customers.change_payment'), require_POST | test_module05.py | CODE/REFERENCE; chưa E2E từng route |
| management/transactions/ | customers.business_views.transactions | StockMovement | capability_required('customers.view_stockmovement') | test_module06.py | CODE/REFERENCE; chưa E2E từng route |
| management/stock/<str:kind>/ | customers.business_views.stock_list | model | capability_required('customers.view_stockmovement') |  | CODE/REFERENCE; chưa E2E từng route |
| management/stock/<str:kind>/add/ | customers.business_views.stock_add |  | capability_required('customers.view_stockmovement') |  | CODE/REFERENCE; chưa E2E từng route |
| management/stock/<str:kind>/<int:pk>/ | customers.business_views.stock_detail |  | capability_required('customers.view_stockmovement') | test_business.py | CODE/REFERENCE; chưa E2E từng route |
| management/stock/<str:kind>/<int:pk>/confirm/ | customers.business_views.stock_confirm |  | capability_required('customers.view_stockmovement'), require_POST | test_business.py, test_module06.py | CODE/REFERENCE; chưa E2E từng route |
|  | customers.views.home | Combo, Promotion, RestaurantInfo, Review |  | test_ai01_ai02.py | CODE/REFERENCE; chưa E2E từng route |
| menu/ | customers.views.menu |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| menu/<int:dish_id>/ | customers.views.food_detail |  |  | test_customer_booking_workspace.py, test_seo.py | CODE/REFERENCE; chưa E2E từng route |
| login/ | customers.views.login_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| register/ | customers.views.register |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| logout/ | customers.views.logout_view |  | require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| staff/ | customers.views.staff_home |  | role_required('ADMIN', 'MANAGER', 'STAFF') | test_grouped_workspace.py, test_operations.py, test_service_assignment_flow.py, test_staff_portal.py | CODE/REFERENCE; chưa E2E từng route |
| account/ | customers.views.profile |  | login_required | test_staff_portal.py | CODE/REFERENCE; chưa E2E từng route |
| invoices/ | customers.payment_views.customer_invoices | service_scope | login_required | test_module05.py | CODE/REFERENCE; chưa E2E từng route |
| invoices/<int:pk>/ | customers.payment_views.customer_invoice |  | login_required | test_customer_booking_workspace.py, test_module05.py | CODE/REFERENCE; chưa E2E từng route |
| invoices/<int:pk>/payments/start/ | customers.payment_views.customer_payment_start |  | login_required, require_POST | test_customer_booking_workspace.py, test_module05.py | CODE/REFERENCE; chưa E2E từng route |
| payments/<int:pk>/report/ | customers.payment_views.customer_payment_report |  | login_required, require_POST | test_module05.py | CODE/REFERENCE; chưa E2E từng route |
| payments/<int:pk>/qr-demo/ | customers.payment_views.customer_payment_qr | service_scope | login_required | test_module05.py | CODE/REFERENCE; chưa E2E từng route |
| management/accounts/ | customers.views.account_list | User | role_required('ADMIN') |  | CODE/REFERENCE; chưa E2E từng route |
| management/accounts/<int:user_id>/edit/ | customers.views.account_edit |  | role_required('ADMIN') | tests.py, test_module02.py | CODE/REFERENCE; chưa E2E từng route |
| management/areas/ | customers.management_views.areas | Area | capability_required('customers.view_area') |  | CODE/REFERENCE; chưa E2E từng route |
| management/areas/add/ | customers.management_views.area_add |  | capability_required('customers.add_area') |  | CODE/REFERENCE; chưa E2E từng route |
| management/areas/<int:pk>/edit/ | customers.management_views.area_edit |  | capability_required('customers.change_area') | test_module02.py | CODE/REFERENCE; chưa E2E từng route |
| management/tables/ | customers.management_views.tables | service_scope | capability_required('customers.view_restauranttable') |  | CODE/REFERENCE; chưa E2E từng route |
| management/tables/add/ | customers.management_views.table_add |  | capability_required('customers.add_restauranttable') |  | CODE/REFERENCE; chưa E2E từng route |
| management/tables/<int:pk>/edit/ | customers.management_views.table_edit |  | capability_required('customers.change_restauranttable') | test_module02.py | CODE/REFERENCE; chưa E2E từng route |
| management/bookings/ | customers.management_views.bookings | service_scope | capability_required('customers.view_booking') | test_grouped_workspace.py | CODE/REFERENCE; chưa E2E từng route |
| management/bookings/<int:pk>/ | customers.management_views.booking_detail | service_scope | capability_required('customers.view_booking') | test_module03.py, test_preorder.py | CODE/REFERENCE; chưa E2E từng route |
| management/bookings/<int:pk>/status/ | customers.management_views.booking_status | service_scope | capability_required('customers.change_booking'), require_POST | test_module02.py | CODE/REFERENCE; chưa E2E từng route |
| management/ | customers.views.management |  | login_required |  | CODE/REFERENCE; chưa E2E từng route |
| management/menu/add/ | customers.views.admin_menu_form |  | role_required('ADMIN', 'MANAGER', 'STAFF') |  | CODE/REFERENCE; chưa E2E từng route |
| management/menu/<int:dish_id>/edit/ | customers.views.admin_menu_form |  | role_required('ADMIN', 'MANAGER', 'STAFF') |  | CODE/REFERENCE; chưa E2E từng route |
| management/menu/<int:dish_id>/availability/ | customers.views.admin_menu_toggle |  | capability_required('customers.change_menuitem'), require_POST |  | CODE/REFERENCE; chưa E2E từng route |
| cart/ | customers.views.cart |  |  | test_module07.py | CODE/REFERENCE; chưa E2E từng route |
| cart/<int:dish_id>/ | customers.views.update_cart | MenuItem, Topping | require_POST | test_customer_booking_workspace.py, test_final_phase.py, test_module07.py, test_seo.py | CODE/REFERENCE; chưa E2E từng route |
| booking/ | customers.views.booking |  | login_required | test_grouped_workspace.py, test_module07.py, test_service_assignment_flow.py | CODE/REFERENCE; chưa E2E từng route |
| booking/<int:booking_id>/cancel/ | customers.views.cancel_booking |  | login_required, require_POST | test_booking_flow.py, test_module03.py, test_preorder.py | CODE/REFERENCE; chưa E2E từng route |
| about/ | customers.module07_views.about | RestaurantInfo |  | test_module07.py | CODE/REFERENCE; chưa E2E từng route |
| offers/ | customers.module07_views.offers | Promotion |  | test_module07.py | CODE/REFERENCE; chưa E2E từng route |
| django-admin/ | django.contrib.admin.sites.index |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/login/ | django.contrib.admin.sites.login |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/logout/ | django.contrib.admin.sites.logout |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/password_change/ | django.contrib.admin.sites.password_change |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/password_change/done/ | django.contrib.admin.sites.password_change_done |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/autocomplete/ | django.contrib.admin.sites.autocomplete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/jsi18n/ | django.contrib.admin.sites.i18n_javascript |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/r/<path:content_type_id>/<path:object_id>/ | django.contrib.contenttypes.views.shortcut |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/booking/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/booking/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/booking/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/booking/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/booking/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/booking/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/category/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/category/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/category/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/category/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/category/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/category/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/menuitem/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/menuitem/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/menuitem/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/menuitem/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/menuitem/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/menuitem/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/user/<id>/password/ | django.contrib.auth.admin.user_change_password |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/user/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/user/add/ | django.contrib.auth.admin.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/user/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/user/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/user/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/user/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/group/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/group/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/group/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/group/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/group/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/auth/group/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/area/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/area/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/area/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/area/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/area/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/area/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/restauranttable/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/restauranttable/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/restauranttable/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/restauranttable/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/restauranttable/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/restauranttable/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/bookingitem/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/bookingitem/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/bookingitem/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/bookingitem/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/bookingitem/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/bookingitem/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/supplier/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/supplier/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/supplier/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/supplier/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/supplier/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/supplier/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/ingredient/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/ingredient/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/ingredient/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/ingredient/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/ingredient/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/ingredient/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/recipeingredient/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/recipeingredient/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/recipeingredient/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/recipeingredient/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/recipeingredient/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/recipeingredient/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/order/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/order/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/order/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/order/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/order/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/order/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/orderitem/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/orderitem/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/orderitem/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/orderitem/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/orderitem/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/orderitem/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/invoice/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/invoice/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/invoice/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/invoice/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/invoice/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/invoice/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/payment/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/payment/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/payment/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/payment/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/payment/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/payment/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceipt/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceipt/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceipt/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceipt/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceipt/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceipt/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceiptitem/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceiptitem/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceiptitem/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceiptitem/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceiptitem/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockreceiptitem/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissue/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissue/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissue/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissue/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissue/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissue/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissueitem/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissueitem/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissueitem/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissueitem/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissueitem/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockissueitem/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockmovement/ | django.contrib.admin.options.changelist_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockmovement/add/ | django.contrib.admin.options.add_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockmovement/<path:object_id>/history/ | django.contrib.admin.options.history_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockmovement/<path:object_id>/delete/ | django.contrib.admin.options.delete_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockmovement/<path:object_id>/change/ | django.contrib.admin.options.change_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/customers/stockmovement/<path:object_id>/ | django.views.generic.base.view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/^(?P<app_label>customers/auth)/$ | django.contrib.admin.sites.app_index |  |  |  | CODE/REFERENCE; chưa E2E từng route |
| django-admin/(?P<url>.*)$ | django.contrib.admin.sites.catch_all_view |  |  |  | CODE/REFERENCE; chưa E2E từng route |
