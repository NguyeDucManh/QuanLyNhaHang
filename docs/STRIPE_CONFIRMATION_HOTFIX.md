# Stripe trả về nhưng cọc vẫn chờ xác nhận

Thanh toán không được xác nhận từ URL success hoặc Session ID do trình duyệt gửi.
Hai nguồn chứng cứ được chấp nhận là webhook ký hợp lệ và truy vấn Stripe API
được xác thực bằng key phía server. Cả hai dùng chung transaction ghi nhận cọc,
khóa booking/deposit/attempt, kiểm tra bàn và hạn giữ bàn, idempotency và audit.

Khi khách quay về trang cọc/success hoặc thăm dò trạng thái, server lấy Session ID
đã lưu của **đúng booking thuộc khách đang đăng nhập**, truy vấn Stripe và mở rộng
PaymentIntent. Chỉ ghi SUCCEEDED khi đồng thời khớp TEST mode, complete/paid,
client_reference_id, metadata (booking/deposit/customer/attempt), amount_total,
currency vnd và PaymentIntent succeeded/amount_received/metadata tương ứng.
Kiểm tra lại dữ liệu sau khi khóa trước commit. Không nhận Session tùy ý từ query.

Nếu còn hạn và bàn phù hợp, booking được CONFIRMED và trình duyệt tự chuyển sang
trang xác nhận. Nếu đã hết hạn/hủy hoặc bàn xung đột, cọc được ghi nhận nhưng cần
đối soát; không tự giành lại bàn. Nếu Stripe chưa trả tiền hoặc API lỗi, giữ trạng
thái chờ, không tạo thanh toán giả. Không ghi StripeWebhookEvent giả cho API read;
audit riêng STRIPE_API_RECONCILED phân biệt rõ nguồn. Webhook đến sau không ghi
nhận cọc/xác nhận booking lần hai.

Giao diện chờ không có form trả cọc mới. Phiên đang mở chỉ có thao tác tiếp tục
đúng phiên cũ; backend lấy lại Session và từ chối mở lại khi complete. Polling
kiểm tra JSON/HTTP và chỉ điều hướng khi server trả confirmed=true; lỗi mạng hoặc
chờ quá lâu hiển thị hướng dẫn kiểm tra/liên hệ, không yêu cầu thanh toán trùng.

## Webhook vẫn cần cho trường hợp khách không quay về

Local: Stripe CLI phải dùng cùng tài khoản TEST với ứng dụng. Signing secret của
CLI hiện tại được truyền trong memory cho Django, không trộn secret endpoint
Dashboard hoặc thay `.env` tự động. Helper mới mặc định chỉ kiểm tra tài khoản:

```sh
python scripts/stripe_local_listener.py --env-file PATH_TO_LOCAL_ENV
```

Sau khi chủ máy dừng server local cũ, thêm `--run` để helper mở listener và Django
ở 127.0.0.1:8000. Helper không dừng server khác và từ chối nếu port đã chiếm dụng.
`--credential-source application-key` dùng key ứng dụng trực tiếp cho CLI; key có
thể thiếu quyền Debugging Tools Write. Không nới quyền hoặc chuyển tài khoản tự
động. `--test-database test_stripe_hotfix_NAME --port 8003` chỉ trỏ tới DB test đã
có; helper không tạo DB hoặc migration. Không chạy helper này trên Render.

Render: giữ endpoint HTTPS `/stripe/webhook/`, key TEST và signing secret đúng
endpoint/tài khoản. Code không thay secrets, feature flags hoặc cấu hình Render.
Log webhook chỉ gồm event ID/type, HTTP status và outcome, không payload/chữ ký
hoặc thông tin thẻ. 400 là chữ ký/payload không hợp lệ; 409 là lệch dữ liệu cọc;
503 là chưa có cấu hình; 500 là handler thất bại và cần retry, transaction rollback.

Không tự phát lại hoặc chỉnh giao dịch cũ. Booking đã hết hạn cần đối soát theo
policy dù Stripe xác nhận đã thu tiền. Không thanh toán lại chỉ để thử bản sửa.

Nguồn chính thức: [Stripe Checkout fulfillment](https://docs.stripe.com/checkout/fulfillment),
[Stripe CLI forwarding](https://github.com/stripe/stripe-cli/wiki/Listen-command).

Không có migration mới, không thay thực đơn/giá/ảnh/recipe, không seed hoặc deploy.
