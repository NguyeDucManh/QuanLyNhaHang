# Issue 10: payments, Vietnamese text and FaceID readiness

This branch includes all four commits of PR9 without merging that PR or changing
main. Do not merge PR9 again without comparing its tree/diff.

No menu/catalog/recipe/price/image data or menu behavior is changed. No operational
seed command, production migration, payment, attendance or schedule is executed by
this change. PostgreSQL source/Render are audited separately; test writes use a
disposable PostgreSQL database only.

## Stripe

`python manage.py check_stripe_config` reports format/readiness and the webhook
path without values, provider calls or database writes. It does not verify real
API permissions or webhook delivery. Hosted Checkout does not require a
publishable key. Set these through the existing service owner, not in Git:

- STRIPE_SECRET_KEY: an actual sk_test_ or adequately scoped rk_test_ key.
- STRIPE_WEBHOOK_SECRET: whsec_ signing secret belonging to this TEST endpoint.
- STRIPE_PUBLIC_BASE_URL: https://smart-restaurant-demo.onrender.com on Render;
  http://127.0.0.1:8000 on local. HTTPS and a configured host are required on Render.

In Stripe Dashboard, select the intended sandbox/Test Mode account, create a
webhook destination for `https://smart-restaurant-demo.onrender.com/stripe/webhook/`
and events checkout.session.completed, checkout.session.async_payment_succeeded,
checkout.session.async_payment_failed, checkout.session.expired. Copy its signing
secret into the existing Render environment only after owner review. Stripe CLI
forwarding uses its own whsec_ and does not prove the hosted endpoint is configured.
Do not send credentials in screenshots or logs.

The page now distinguishes configuration, expiry, reconciliation and non-payable
booking states. Expired deposits cannot be made payable by changing CSS or keys.
Only verified signed webhook processing confirms payment; success redirect does
not. Existing idempotency/amount/currency/ownership/signature tests remain required.
No payment or scheduler catch-up is run against production for this PR.

## Vietnamese

Repair irreversible question marks in booking_payment.html, remove emitting HTML
BOMs outside menu pages, use a system Vietnamese-capable font for the deposit
heading and preserve tone-mark line height. The source audit checks UTF-8/NFC and
known damage patterns. Python BOMs are valid and historical/menu files stay intact.
`python scripts/check_vietnamese_text.py` is also part of Ubuntu CI. Source checks
do not replace real browser/device glyph and screenshot review.

## Confirmed existing staff identities

Two real existing accounts were confirmed by the owner in the Issue10 work:
QuocHuy and VanQuyet still carry legacy DEMO-prefixed employee codes. Do not
rename codes, remove historical rows, create replacement users, or disable FaceID.
The reviewed identity service records an idempotent audit tied to employee ID,
user ID and the current code. A changed identity invalidates that confirmation.
Operational identity checks accept a reviewed profile without rewriting history;
face matching, active staff roles, approved shifts and attendance windows remain.

Preview only (replace IDs/actor after reading the correct environment inventory):

```sh
python manage.py confirm_staff_identity --employee ID --actor ADMIN_USERNAME --reason 'Owner verified the existing staff identity'
```

The same command with --apply writes the confirmation audit only after data
approval, backup and target verification. It does not enroll a face, approve a
schedule, create Attendance or pay payroll. Preview mode does not grant privileges.
No new schema is required for this confirmation; it reuses AuditLog.

## Deployment status

Code/test readiness, CI, Render deployment and production data updates are separate
states. PR review/green CI does not authorize merge/deploy or migration 0022–0024.
Keep the existing three feature flags false and secrets unchanged. A failed or
missing camera/model/shift must remain an actionable error, not a fake recognition.
