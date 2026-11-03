# Smart Restaurant — Giai đoạn AI

Các service AI chạy CPU. Không train hoặc tải model khi khởi động server hay mở trang. Dữ liệu mô phỏng chỉ nằm trong `ai_models/datasets`, không tạo Customer/Order/StockMovement/Attendance giả trong PostgreSQL vận hành.

## Mở giao diện

- Manager/Admin: `/management/ai/`, `/management/ai/forecast/`, `/management/ai/inventory/`, `/management/ai/faces/`, `/management/recommendations/`.
- Customer: `/recommendations/` và `/ai/chat/`. Panel hỗ trợ phân biệt **Trợ lý AI** và **Nhắn nhân viên**.
- Employee: `/work/faceid/`. Camera cần localhost hoặc HTTPS; phải đăng nhập đúng tài khoản nhân viên.

## Tái chạy thí nghiệm

Trong PowerShell tại thư mục project:

```powershell
.\.venv\Scripts\python.exe manage.py migrate --noinput
.\.venv\Scripts\python.exe manage.py download_ai_models --assets-cache D:\SmartRestaurant-AI-cache\face-assets --embedding-cache D:\SmartRestaurant-AI-cache\paraphrase-multilingual-MiniLM-L12-v2-e8f8c211
.\.venv\Scripts\python.exe manage.py prepare_ai_research_data --seed 42 --days 70 --interactions 280 --end-date 2026-10-12
.\.venv\Scripts\python.exe manage.py train_recommendation_models
.\.venv\Scripts\python.exe manage.py train_forecast_models
.\.venv\Scripts\python.exe manage.py rebuild_chatbot_index
.\.venv\Scripts\python.exe manage.py evaluate_ai_models
.\.venv\Scripts\python.exe scripts\ai_final_checks.py
```

Để dùng dữ liệu cập nhật, bỏ `--end-date` hoặc chọn ngày kết thúc phù hợp. Cùng seed, ngày kết thúc và snapshot DB/menu cho ra cùng dữ liệu. Mỗi lần prepare/train/evaluate tạo thư mục version mới; `latest.json` chỉ cập nhật sau khi artifact hoàn tất. `AI_MODEL_ROOT` có thể cấu hình bằng Django settings cho thí nghiệm riêng.

Không cần cài lại stack AI đã chuẩn bị. `requirements.txt` ghi đúng phiên bản môi trường đã kiểm tra. Dependency thêm duy nhất là **websocket-client 1.9.2**, dành cho kiểm thử Chrome và nằm trong `requirements-dev.txt`; không dùng trong service AI.

## Recommendation

Giữ nguyên `customers/recommendation_service.py` cho content-based và kiểm thử cũ. `customers/ai/collaborative_service.py` xây user-item matrix và item-item cosine; `hybrid_service.py` kết hợp content vectors category/price band/recipe ingredients với collaborative.

Mỗi purchase event có trọng số:

`(1 + ln(1 + quantity)) × (1 + 0.125 × (rating - 3)) × exp(-ln(2) × age_days / 90)`.

Các purchase event cùng user/item được cộng, phản ánh tần suất, số lượng, rating và recency. Thử α = 0.25/0.50/0.75 trên validation; chọn theo NDCG@5. Test cuối chỉ đánh giá. Split **toàn cục theo thời gian**, không shuffle; cosine/content profiles không chứa tương tác holdout. Các feature catalog dùng menu hiện tại, không tái dựng lịch sử menu. Greedy diversity dùng penalty 0.12 theo category; loại món unavailable/category inactive/chưa có giá. Customer mới dùng popularity/review/content fallback; ít history dùng content; ≥2 món history dùng hybrid. Runtime refresh giao dịch thật từ DB, dùng bộ mô phỏng đã ghi nhãn làm dữ liệu nghiên cứu cộng đồng.

Timestamp split so sánh instant, không so sánh chuỗi ISO khác offset. Dữ liệu prepare chuẩn hóa UTC; purchase có review chỉ khả dụng tại `max(purchased_at, review.created_at)` để không đưa rating tương lai vào tập train. Trọng số recency tính từ thời điểm interaction khả dụng.

Precision/Recall/F1/NDCG là trung bình trên user test đủ history. Dataset nhỏ, chủ yếu synthetic; không coi metrics này là chất lượng thương mại trên khách thật.

## Forecast và inventory

Train Linear Regression, Random Forest và XGBoost cho doanh thu, số đơn và 15 menu có recipe. Lag 1/7/14 và rolling mean 7/14 đều **shift từ quá khứ**. Split 49/10/11 ngày; 14 ngày đầu chưa đủ lag bị loại khỏi feature train. Validation/test dùng dự báo đệ quy, không lấy actual holdout để làm lag; future promotion là covariate biết trước trong thí nghiệm, mặc định 0 trong inference. Chọn model bằng validation MAE; bảng test không được dùng chọn model. Production model sau đánh giá được refit trên lịch sử đầy đủ. MAPE loại denominator 0, công bố số mẫu bị loại.

Forecast bắt đầu từ ngày sau ngày cuối dataset, không tự dịch sang ngày hiện tại. Cần prepare/train lại khi dataset cũ. 30 ngày chỉ là thăm dò, không có prediction interval hay cam kết độ chính xác. Dataset hiện trộn 1 ngày doanh số thật nhỏ với 69 ngày mô phỏng lớn hơn; MAPE test rất cao và cần được giữ nguyên trong báo cáo.

Inventory không train model riêng. `predicted_usage = Σ(predicted_menu_quantity × recipe_quantity_required)`, đơn vị recipe trùng đơn vị Ingredient. Tính nhu cầu/ngày, safety stock, reorder point, shortage và mua đề xuất. Safety days 3/5/7; lead time 1–30 ngày cấu hình theo Ingredient/Supplier, mặc định **giả định 2 ngày** khi chưa cấu hình. `reorder_point = average_daily_usage × lead_time + max(safety_stock, minimum_stock)`; mua `max(0, demand + max(safety_stock, minimum_stock) - current_stock)`. Piece/portion làm tròn lên nguyên, đơn vị khác làm tròn lên 0.001. Risk CRITICAL khi thiếu nhu cầu horizon, HIGH khi chưa đủ lead-time demand, LOW dưới reorder point, còn lại NORMAL. Đánh dấu nguyên liệu chưa được các món forecast bao phủ. What-if +10%/+20% chỉ preview; không tạo phiếu nhập hoặc sửa tồn kho.

## FaceID

Nguồn cache, revision và SHA-256 đầy đủ: `ai_models/pretrained/manifest.json`. Máy hiện tại cache pretrained ở `D:\SmartRestaurant-AI-cache` vì ổ C thiếu dung lượng; metadata/artifact nghiên cứu vẫn trong project. Không có `facenet-pytorch`.

- [FaceNet ONNX community export](https://github.com/NicolasSM-001/faceNet.onnx-) tại commit `b019d5bf79ddb3805f77f7650885b710b333b433`, input RGB NHWC 160×160, chuẩn hóa mean/std theo ảnh, output 128-d L2 normalized.
- SHA-256 FaceNet: `1c69044bdbf849aa58fb27df62fe0cc0d23648411192c6f63e8b764033b552a6`.
- [MediaPipe Face Landmarker](https://ai.google.dev/edge/mediapipe/solutions/vision/face_landmarker/python), model `float16/1`; SHA-256 `64184e229b263107bc2b804c6625db1341ff2bb731874b0bcc2fe6544e0bc9ff`.

Upstream FaceNet export không có model card đầy đủ về tập pretraining/license; không tự tuyên bố nguồn tập train hay accuracy benchmark. Đã kiểm tra tải/inference CPU và hình dạng tensor. Vẫn cần kiểm chứng nhận diện bằng người thật trong môi trường nhà hàng.

UI tự thu 15 frame đạt quality; server kiểm tra đúng 1 mặt, kích thước ≥80 px, blur, brightness, yaw và embedding consistency. Lưu embedding JSON + quality + hash, không lưu ảnh gốc và không trả embedding cho frontend. Đăng ký lại thay samples cũ trong transaction và xóa threshold calibration cũ.

**Chưa có ảnh người thật: 0 hồ sơ/0 embedding/không có threshold hoặc FaceID metrics.** Đăng ký trước, sau đó chuẩn bị bốn thư mục ảnh riêng, mỗi thư mục ≥5 ảnh. Ảnh enrollment/validation/test phải khác nhau; kiểm tra bằng hash file. Các ảnh impostor phải là người khác với Employee đang hiệu chỉnh, không gán nhãn tự động.

```powershell
.\.venv\Scripts\python.exe manage.py calibrate_faceid --employee 1 --validation-genuine <folder> --validation-impostor <folder> --test-genuine <folder> --test-impostor <folder>
```

Command thử thresholds 0.40–0.95, chọn bằng FAR+FRR trên validation; công bố accuracy/precision/recall/F1/FAR/FRR từ test riêng và lưu model version/image hashes. Hash không phát hiện ảnh cùng nội dung đã resize/encode lại; người chuẩn bị dữ liệu phải bảo đảm không trùng người/frame giữa các partition theo mục đích thí nghiệm.

Liveness ngẫu nhiên blink/left/right yêu cầu neutral → action → neutral trên nhiều frame do **server** trích landmark. Challenge gắn actor, hết hạn 90 giây, dùng một lần kể cả fail. Mỗi frame phải khớp cùng profile; threshold chưa calibrate thì không chấm công. Server xác định Employee, kiểm tra owner và WorkSchedule rồi gọi `personnel_service.punch` hiện có. Không tin `employee_id`/`verified=true` của client. Audit có identity/score/threshold/liveness/action/rejection reason, không lưu ảnh. Quality và identity-margin heuristics là cấu hình demo, chưa calibration toàn hệ thống. Video replay, virtual camera và anti-spoof nâng cao chưa được giải quyết; liveness này không phải biometric cấp ngân hàng.

## AI assistant và evaluation

Input guard → intent router + fuzzy entities → memory → query rewrite → closed business tools hoặc RAG → semantic/BM25 rerank → extractive grounded answer → concise guard → human handoff.

Các tool/schema đóng nằm trong `tool_registry.py`: menu/price/detail/combo/promotion/restaurant info, booking availability, own booking/order/payment, cart view/add, hybrid recommendation. Giá và trạng thái đọc DB tại thời điểm hỏi. Ownership luôn lọc user đang đăng nhập; anonymous phải login cho dữ liệu cá nhân. Cart HTTP và AI cùng dùng `cart_service.add_to_cart`; booking dùng service availability/row locks sẵn có, chỉ preview và dẫn sang form xác nhận.

21 intents trong `intent_router.py`. Memory/history dùng AIConversation/AIMessage riêng, gắn user + session, không trộn human chat. Ambiguous `7h` hỏi sáng/tối; ngày/guest_count được giữ qua lượt sau. Không có external LLM/API; answer từ tool results hoặc nguyên văn context đã qua threshold. Đây là lựa chọn grounded/extractive CPU, khả năng hiểu ngôn ngữ vẫn bị giới hạn bởi router và entity parsing. Không tự dựng giá/voucher/status. Injection/secrets/cross-user/payroll bị chặn. RAG chỉ index các trường công khai và policy có nguồn code/hash; không index User/Payroll/FaceEmbedding/.env.

[Embedding multilingual MiniLM](https://huggingface.co/sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2): `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, CPU, safetensors local, kiểm tra SHA-256 khi load. FAISS cosine/IP Top 10 → rerank `0.65 semantic + 0.25 normalized BM25 + 0.10 token coverage` → tối đa 3 context. Semantic threshold 0.42; UNKNOWN thêm kiểm tra lexical coverage ≥0.60 và semantic ≥0.55 để từ chối không đủ dữ liệu. Thresholds retrieval hiện là heuristic, chưa có bộ validation độc lập để hiệu chỉnh.

`evaluate_ai_models` lưu câu hỏi, expected assertions, results, 45 multi-turn conversations và mẫu chấm tay trong artifact. Câu hỏi template tạo từ DB/policy, **không phải 274 câu user thật độc lập**. Intent/tool/Hit@5/refusal đo trực tiếp. Answer correctness kiểm tra chuỗi entity/giá/giờ kỳ vọng; groundedness đo nguồn hiện diện; hallucination chỉ là proxy assertion giá/giờ/combo. Các chỉ số này không thay thế chấm tay, không đánh giá toàn bộ phát biểu của chatbot. Câu hỏi không có assertion bị loại khỏi answer correctness.

## Verification và giới hạn demo

`scripts/ai_final_checks.py` lưu exit code/duration/log cho check, migration drift, migrate, full regression và pip check trong `ai_verification/`. `scripts/ai_browser_smoke.py` tạo PostgreSQL tạm riêng, xóa khi kết thúc, không ghi fixture vào database chính. Kiểm tra Chrome DOM/layout desktop 1440 và mobile 390, đồng thời kiểm tra chat HTTP/CSRF bằng Django Client.

Chrome navigation localhost hiện bị `ERR_ABORTED`, captureScreenshot bị timeout trên máy này. Kiểm tra render dùng HTML/CSS/JS local inject vào Chrome; **không tuyên bố live browser end-to-end PASS**. Webcam thật, enrollment thật, unknown người thật và liveness thật cần người dùng kiểm tra sau khi chuẩn bị ảnh/calibration. GPS/GIS/Haversine/Leaflet không thuộc giai đoạn này.

Kết quả hiện tại và metrics chi tiết: `docs/AI_REPORT.md`, các JSON version trong `ai_models/`, browser checks trong `qa_browser/results.json`.


## Cập nhật hoàn thiện 14/10/2026

Xem [FINAL_REPORT.md](FINAL_REPORT.md) và [FINAL_DEMO.md](FINAL_DEMO.md): redesign, chatbot, FaceID UX, GIS và live Edge E2E. Hạn chế browser trong báo cáo cũ là lịch sử; live HTTP đã kiểm tra được ở giai đoạn này. Webcam/GPS thật, enrollment và threshold calibration vẫn chưa được kiểm chứng. Các metric AI cũ giữ nguyên provenance.
