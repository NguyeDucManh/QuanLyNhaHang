# Smart Restaurant — hướng dẫn bản source sạch

Yêu cầu Python **3.14**, PostgreSQL và CPU; không cần GPU. Cần Internet để cài dependencies và tải pretrained lần đầu. Giữ chữ hoa `static/Image` khi chạy Linux.

## Cài đặt Windows

Tạo database PostgreSQL riêng (ví dụ smart_restaurant) và tài khoản có quyền trên database đó:

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
```

Điền SECRET_KEY ngẫu nhiên và thông tin PostgreSQL của bạn trong .env. Bản ZIP không chứa .env thật hoặc mật khẩu người dùng gốc. Môi trường hiện hữu đã cài đúng stack không cần cài lại.

```powershell
python manage.py migrate
python manage.py seed_rbac
python manage.py seed_menu
python manage.py createsuperuser
python manage.py runserver
```

Mở http://127.0.0.1:8000/. Superuser có quyền ADMIN. Đăng ký /register/ tạo CUSTOMER. Tạo STAFF/MANAGER và cấp quyền qua quản trị. Không có mật khẩu demo cố định trong bản nộp. seed_menu thêm 45 món thiếu, không ghi đè giá/ảnh đã sửa. seed_restaurant tùy chọn: xem help trước khi dùng. Không cần seed HR DEMO; dashboard trống có hướng dẫn.

## AI CPU và offline

Giữ manifest, source AI, artifact forecast/recommendation mới nhất và FAISS index trong source. Pretrained cache ngoài project **không đóng gói**. Máy mới cần setup trước khi demo FaceID/RAG:

```powershell
python scripts/setup_models.py --cache-root C:\SmartRestaurant-AI-cache
python manage.py rebuild_chatbot_index
```

FaceNet ONNX revision b019d5bf79ddb3805f77f7650885b710b333b433, MediaPipe face_landmarker float16/1, embedding sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2 revision e8f8c211226b894fcb81acc59f3b34ba3efd5f42. Nguồn/hash tại ai_models/pretrained/manifest.json. Reranker dùng stack hiện hữu, không tải model riêng.

Nếu có cache đúng cấu trúc/hash, cấu hình offline:

```powershell
python scripts/setup_models.py --cache-root D:\SmartRestaurant-AI-cache --reuse-existing
```

Sau setup, model chạy CPU local. Rebuild FAISS sau seed để dùng tài liệu DB mới. Artifact forecast/recommendation là dữ liệu nghiên cứu có provenance; train lại chỉ khi chủ động muốn dùng dữ liệu vận hành mới. Không train lúc startup. Webcam/GPS cần quyền browser; vận hành thật cần Employee xác nhận, consent, enrollment, ca/location policy. Ngưỡng 0,80 tạm thời chưa chứng minh FAR/FRR. OSM tiles cần mạng. Settings phục vụ local demo; production cần cấu hình bảo mật/Redis phù hợp.

## Verification

```powershell
python manage.py check
python manage.py makemigrations --check
python manage.py test --noinput
python -m pip check
python scripts/verify_submission.py
```

verify_submission dùng DB PostgreSQL tạm, cần quyền CREATE DATABASE và chỉ xóa đúng DB tạm đó. requirements-dev.txt chỉ cần cho browser QA; không thay runtime stack. Bản clean đã được smoke test bằng interpreter chuẩn bị sẵn, chưa cài mới toàn bộ dependencies trên máy khác.

## Audit, cache và build

```powershell
python scripts/submission_audit.py
powershell -ExecutionPolicy Bypass -File scripts/cleanup_cache.ps1
powershell -ExecutionPolicy Bypass -File scripts/cleanup_cache.ps1 -Apply
powershell -ExecutionPolicy Bypass -File scripts/build_submission.ps1
```

Audit không xóa file. Cleanup chỉ xóa file CACHE trong manifest, bỏ qua .venv/model/data/source/UNKNOWN/symlink. Build tạo SmartRestaurant_Submission/ và ZIP, không xóa project gốc. Nếu output tồn tại, dùng -OutputName SmartRestaurant_Submission_v2. Bản nộp không có .venv/cache/.env/DB dump/QA/log nặng. Evidence tối thiểu được giữ; references lịch sử trong bản copy trỏ đến archive notice, bằng chứng gốc giữ ở workspace.
