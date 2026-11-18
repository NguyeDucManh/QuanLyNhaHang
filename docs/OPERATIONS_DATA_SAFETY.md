# Dữ liệu vận hành và bộ kiểm thử Issue10

## Bất biến thực đơn

Không chạy seed_menu trên local gốc/Render. Không sửa MenuItem, Category, Topping,
liên kết topping–món, Combo, ComboItem, RecipeIngredient, giá, ảnh, mô tả hoặc
luồng chọn món. Lập baseline từng DB bằng timezone UTC trước/sau để tránh nhầm
khác múi giờ của timestamp thành dữ liệu khác. Không đồng bộ bằng restore đè.

`prepare_operations_catalog` chỉ cho phép **tạo mới** Ingredient, Supplier,
IngredientSupplyPolicy, Position từ manifest có nguồn/xác nhận quản trị; mặc
định preview/dry-run. Không cho nhập current_stock, không sinh phiếu kho hay lịch
sử giao dịch. Trùng tên/mã hoặc hồ sơ hiện có khác dữ liệu sẽ báo xung đột, không
upsert/skip âm thầm. Mỗi apply cần actor có quyền và đúng hash đã duyệt; một
transaction kèm audit và kiểm tra hash toàn bộ menu, lỗi rollback.

```sh
python manage.py prepare_operations_catalog --manifest reviewed-reference-data.json --dry-run
```

Chỉ sau duyệt riêng mới dùng --apply --actor USERNAME --approved-digest HASH.
Không bịa điện thoại/email/địa chỉ nhà cung cấp. Đã có 71 nguyên liệu thì không
thêm trùng để đạt KPI 40–80. Ba nhà cung cấp đã có chưa tự biến thành 5–12 hồ sơ
thật nếu chưa có thông tin xác minh. Bốn khu vực/20 bàn đủ hiện tại: không sửa
bàn đang có booking. Không sửa công thức hay số tồn đã ghi.

## Bộ dữ liệu test tách biệt

Lấy backup read-only local, kiểm tra archive rồi restore vào **database test mới
được định danh rõ**, không restore local gốc hoặc Render. Giữ catalog gốc đúng
snapshot. Chỉ trên bản sao test mới áp dụng migration/fixture/roster đã kiểm thử.
Không upload dump, embeddings, tài khoản/hash mật khẩu hoặc dữ liệu cá nhân vào
GitHub. Backup và kết quả kiểm tra phải Git-ignore.

`build_operations_test_dataset` bị chặn ở smart_restaurant, smart_restaurant_demo,
Render và host không phải loopback; còn cần settings ISSUE10_TEST_FIXTURES_ENABLED.
Nó tái sử dụng tài khoản và catalog bản sao, không seed menu/tạo tài khoản. Các
nhà cung cấp có tên tự nhiên, không điện thoại giả; receipts, purchase orders,
orders/kitchen/invoices/payments/review/promotion và AI supply policies chỉ là
fixture, có audit test-only và idempotency. Không coi chúng là doanh thu, kho thực
tế hoặc review khách hàng thật. Review fixture để ẩn; không thêm Attendance.

```sh
python manage.py build_operations_test_dataset --actor ADMIN_USERNAME --output private-result.json
```

Mặc định không ghi; --apply chỉ được dùng trong sandbox test guard đã cho phép.
Settings scripts.issue10_sandbox_settings chỉ cho DB test_issue10_sandbox_* ở
loopback, dùng cookie/SECRET_KEY riêng và tắt Stripe keys trong process sandbox.
Không chọn settings này ở Render. Ba feature flags production không thay đổi.

Sau khi duyệt code/migrations/dữ liệu, local gốc và Render mới có thể dùng cùng
release. Code/CI PASS không đồng nghĩa deployed hoặc production data updated.
