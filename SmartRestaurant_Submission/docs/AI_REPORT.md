# Báo cáo giai đoạn AI — Smart Restaurant

Dataset `20261013T164031-7087f743`; recommendation `20261013T164033-66fd84d3`; forecast `20261013T164036-a510e288`; RAG `20261013T163822-2226e961`; evaluation `20261013T164050-29731cf4`.

Số dưới đây được đọc từ artifact train/evaluate thật. Phần mô phỏng và các chỉ số proxy được ghi riêng.

## Recommendation

5 interaction thật + 275 SYNTHETIC. Seed 42. Best α = 0.25 (validation NDCG@5).

| Model | Users test (real / simulated) | Precision@5 | Recall@5 | F1@5 | NDCG@5 |
|---|---:|---:|---:|---:|---:|
| Content-Based | 0 / 23 | 0.026087 | 0.086957 | 0.039337 | 0.064403 |
| Collaborative | 0 / 23 | 0.043478 | 0.123188 | 0.062629 | 0.105163 |
| Hybrid | 0 / 23 | 0.060870 | 0.195652 | 0.091097 | 0.109581 |

Các user có history thật hiện chưa đủ cho temporal test; kết quả chủ yếu trên khách mô phỏng, không được gọi là metrics khách thật.

## Forecast

1 ngày thật + 69 SYNTHETIC, liên tục 2026-08-04 → 2026-10-12; 15 món có recipe × 70 ngày. Seed 42.

| Target | Model | MAE | RMSE | MAPE (%) |
|---|---|---:|---:|---:|
| revenue | Linear Regression | 18,107,943.275434 | 23,931,861.011998 | 417.371531 |
| revenue | Random Forest | 16,395,897.710877 | 22,680,837.584829 | 387.156107 |
| revenue | XGBoost | 19,717,040.727273 | 25,824,359.326788 | 401.269728 |
| order_count | Linear Regression | 3.594203 | 5.045776 | 123.979080 |
| order_count | Random Forest | 3.956047 | 5.230353 | 135.172531 |
| order_count | XGBoost | 4.103956 | 5.523404 | 141.130926 |

Best `revenue`: **Linear Regression**, chọn theo validation MAE; train ['2026-08-04', '2026-09-21'], validation ['2026-09-22', '2026-10-01'], test ['2026-10-02', '2026-10-12'].
Best `order_count`: **Random Forest**, chọn theo validation MAE; train ['2026-08-04', '2026-09-21'], validation ['2026-09-22', '2026-10-01'], test ['2026-10-02', '2026-10-12'].

MAPE cao được giữ nguyên: tập test có ngày doanh số thật thấp hơn nhiều các ngày mô phỏng. Không có tuyên bố accuracy 99%. Model chưa chứng minh chất lượng dự báo vận hành. Forecast 30 ngày chỉ thăm dò, không có prediction interval. Actual/Predicted và feature importance/coefficient của cả ba model lưu trong metadata và UI.

| Món | Model chọn | MAE test | RMSE test | MAPE test (%) |
|---|---|---:|---:|---:|
| Súp bào ngư hải sâm | Random Forest | 1.455106 | 1.888272 | 44.816807 |
| Súp cua tuyết trứng cá | Random Forest | 1.939452 | 2.285713 | 113.413325 |
| Gỏi cá hồi sốt mè rang | XGBoost | 2.178428 | 2.795847 | 61.275601 |
| Gỏi sò điệp kiểu Nhật | Linear Regression | 1.614149 | 1.803963 | 78.629255 |
| Mắt cá ngừ đại dương hầm thuốc Bắc | Linear Regression | 1.569749 | 1.890666 | 77.660756 |
| Bào ngư sốt dầu hào | XGBoost | 1.774344 | 2.005093 | 57.348853 |
| Hải sâm hầm nấm đông cô | Random Forest | 2.981713 | 3.418599 | 110.382596 |
| Sò điệp áp chảo sốt chanh bơ | XGBoost | 2.139118 | 2.873189 | 110.778737 |
| Tôm hùm nướng phô mai | Linear Regression | 2.237607 | 3.223250 | 73.780802 |
| Tôm hùm sốt bơ tỏi | XGBoost | 2.126660 | 2.792386 | 67.083930 |
| Cua sốt tiêu đen | XGBoost | 3.226755 | 3.544153 | 144.275871 |
| Cua rang sốt trứng muối | XGBoost | 1.346269 | 1.502289 | 57.336376 |
| Hàu nướng phô mai | Random Forest | 2.311127 | 2.685288 | 80.742432 |
| Bạch tuộc nướng sốt cay | XGBoost | 1.719568 | 2.139466 | 54.035958 |
| Cá hồi áp chảo sốt chanh dây | XGBoost | 1.396499 | 1.654745 | 56.526150 |

## AI Inventory

Đánh giá 71 Ingredient. Risk: `{"NORMAL": 62, "CRITICAL": 8, "LOW": 1}`.

Policy mặc định lead time **2 ngày (giả định, chưa gán Supplier)**; safety **3 ngày**, cho phép 3/5/7. Có UI gán Supplier/lead time/safety theo Ingredient. Reorder point = daily demand × lead time + max(safety stock, minimum stock). What-if +10%/+20% chỉ preview. Không sửa stock, không tự tạo phiếu nhập. Demand chỉ phủ 15 món recipe; nguyên liệu khác được đánh dấu chưa bao phủ.

| Nguyên liệu | Đơn vị | Usage 7 ngày | Đề xuất mua | Risk |
|---|---|---:|---:|---|
| Tôm hùm | kg | 13.529288 | 16.328000 | CRITICAL |
| Lòng đỏ trứng muối | piece | 35.542741 | 11.000000 | NORMAL |
| Cá hồi | kg | 4.598814 | 2.570000 | CRITICAL |
| Bơ | kg | 2.114063 | 2.115000 | CRITICAL |
| Chanh dây | kg | 0.526556 | 0.527000 | LOW |

## FaceID

Pretrained FaceNet ONNX, RGB 160×160 → embedding 128-d L2, ONNX Runtime CPU. 0 Employee enrolled; 0 embedding thật. Threshold: **chưa calibrate**.

**Chưa đủ dữ liệu khuôn mặt thật để công bố metrics.** Không có accuracy/precision/recall/F1/FAR/FRR giả. Cần enrollment thật 10–20 frame/người và bốn tập ảnh validation/test genuine/impostor riêng (≥5 ảnh/tập/người) để chạy `calibrate_faceid`. Tests hiện kiểm tra pipeline/ownership/liveness/service integration bằng fixtures và mocks; không coi đó là accuracy nhận diện người thật.

FaceNet revision `b019d5bf79ddb3805f77f7650885b710b333b433`, SHA-256 `1c69044bdbf849aa58fb27df62fe0cc0d23648411192c6f63e8b764033b552a6`.

Liveness basic: random blink/left/right, neutral → action → neutral, landmark được server trích; challenge gắn actor, 90 giây, một lần. Server xác định Employee và gọi Attendance service cũ. Camera thật/video spoof chưa đánh giá; không phải anti-spoof cấp cao. Upstream community ONNX export chưa có model card đầy đủ về training/license.

## AI Chatbox

21 intents: `GREETING, MENU_SEARCH, MENU_PRICE, MENU_DETAIL, MENU_RECOMMENDATION, COMBO_INFO, PROMOTION_INFO, RESTAURANT_INFO, OPENING_HOURS, BOOKING_POLICY, BOOKING_AVAILABILITY, MY_BOOKING, MY_ORDER_STATUS, MY_PAYMENT_STATUS, CART_ADD, CART_VIEW, WEBSITE_HELP, POLICY, FAQ, OUT_OF_SCOPE, UNKNOWN`.

13 tools/schema đóng: `search_menu, get_menu_price, get_menu_detail, get_combo_info, get_current_promotions, get_restaurant_info, check_booking_availability, get_my_booking, get_my_order_status, get_my_payment_status, get_my_cart, add_to_cart, recommend_for_current_user`.

Guard → router/entities → session/user memory → DB/business tools hoặc sentence-transformers + FAISS → semantic/BM25 rerank → extractive answer → concise guard → human handoff. AIConversation/AIMessage riêng, không trộn human chat. Giá/trạng thái đọc DB live; ownership được kiểm tra; không dùng external LLM/API.

79 documents / 79 chunks. Model `sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2`, revision `e8f8c211226b894fcb81acc59f3b34ba3efd5f42`, CPU. Vector Top 10, rerank Top 3; lexical+semantic reranker.

274 câu evaluation template từ DB/policy + 45 hội thoại. Không phải bộ câu hỏi user thật độc lập.

| Chỉ số | Kết quả |
|---|---:|
| Intent Accuracy | 1.000000 |
| Tool selection accuracy | 1.000000 |
| Retrieval Hit@5 | 1.000000 |
| Answer correctness (assertion proxy) | 0.992218 |
| Out-of-scope/injection refusal accuracy | 1.000000 |
| No-data refusal accuracy | 1.000000 |
| Multi-turn memory accuracy | 1.000000 |
| Hallucination count (price/hour/combo assertion proxy) | 0.000000 |
| Hallucination rate (proxy) | 0.000000 |
| Groundedness (source presence proxy) | 1.000000 |

Có 2 assertion chưa đạt. Chi tiết trong `ai_models/evaluation/20261013T164050-29731cf4/chatbot_results.json`.

Answer correctness là proxy so khớp chuỗi entity/giá/giờ, groundedness là proxy nguồn hiện diện, hallucination chỉ kiểm tra assertion giá/giờ/combo. Câu không có assertion bị loại khỏi correctness. **Không gọi các chỉ số proxy này là đánh giá ngữ nghĩa toàn diện.** Có `manual_review_sample` để người dùng chấm tay. RAG thresholds hiện heuristic, chưa hiệu chỉnh trên validation độc lập. Router/entity parser còn hạn chế; chưa hỗ trợ đầy đủ mọi cách diễn đạt/ngày tương đối.

## System và verification

Migration mới: `customers/migrations/0016_aiconversation_aimessage_faceaudit_facechallenge_and_more.py`; chỉ thêm bảng AI/policy, không xóa dữ liệu nghiệp vụ cũ.

Full regression: **371/371 PASS**, 172.150 giây (331 tests cũ + 40 tests mới).
- `manage.py check`: PASS (1.371s).
- `manage.py makemigrations --check`: PASS (1.413s).
- `manage.py migrate --noinput`: PASS (1.525s).
- `manage.py test --noinput`: PASS (182.153s).
- `-m pip check`: PASS (0.594s).

Counts database vận hành sau triển khai: `{"Order": 1, "OrderItem": 5, "MenuItem": 45, "Employee": 5, "Ingredient": 71}`. Không tạo Order/Customer/Attendance mô phỏng vào DB chính; không sửa stock hay dùng browser fixtures trong DB chính.

Browser: kiểm tra 6 trang × desktop/mobile trong Chrome DOM/layout, không tràn ngang; chat HTTP/CSRF PASS trên PostgreSQL tạm riêng, đã xóa DB tạm. Chrome navigation localhost bị ERR_ABORTED và screenshot bị timeout, nên dùng HTML/CSS/JS inject; **chưa xác nhận live browser end-to-end hoặc webcam thật**. Kết quả máy đọc được: `qa_browser/results.json`.

Dependencies AI được giữ nguyên, ghi đúng installed versions trong requirements.txt. Thêm websocket-client 1.9.2 chỉ để browser QA, requirements-dev.txt. Model/cache ở `D:\SmartRestaurant-AI-cache`, manifest/source/revision/hash nằm trong project.

## Files tạo/sửa

Tạo:
- `customers/ai/__init__.py`
- `customers/ai/artifacts.py`
- `customers/ai/chatbot/__init__.py`
- `customers/ai/chatbot/answer_guard.py`
- `customers/ai/chatbot/assistant_service.py`
- `customers/ai/chatbot/evaluation.py`
- `customers/ai/chatbot/intent_router.py`
- `customers/ai/chatbot/memory_service.py`
- `customers/ai/chatbot/rag_service.py`
- `customers/ai/chatbot/reranker.py`
- `customers/ai/chatbot/tool_registry.py`
- `customers/ai/collaborative_service.py`
- `customers/ai/face/__init__.py`
- `customers/ai/face/evaluation.py`
- `customers/ai/face/face_enrollment_service.py`
- `customers/ai/face/facenet_service.py`
- `customers/ai/face/liveness_service.py`
- `customers/ai/forecast_service.py`
- `customers/ai/hybrid_service.py`
- `customers/ai/inventory_ai_service.py`
- `customers/ai/research_data.py`
- `customers/ai_models.py`
- `customers/ai_phase_views.py`
- `customers/cart_service.py`
- `customers/management/commands/calibrate_faceid.py`
- `customers/management/commands/download_ai_models.py`
- `customers/management/commands/evaluate_ai_models.py`
- `customers/management/commands/prepare_ai_research_data.py`
- `customers/management/commands/rebuild_chatbot_index.py`
- `customers/management/commands/train_forecast_models.py`
- `customers/management/commands/train_recommendation_models.py`
- `customers/migrations/0016_aiconversation_aimessage_faceaudit_facechallenge_and_more.py`
- `customers/test_ai_phase.py`
- `docs/AI_PHASE.md`
- `docs/AI_REPORT.md`
- `requirements-dev.txt`
- `scripts/ai_browser_smoke.py`
- `scripts/ai_final_checks.py`
- `scripts/write_ai_report.py`
- `static/ai/ai.js`
- `templates/admin/ai/chatbot.html`
- `templates/admin/ai/dashboard.html`
- `templates/admin/ai/demand-forecast.html`
- `templates/admin/ai/faces.html`
- `templates/admin/ai/forecast.html`
- `templates/admin/ai/inventory-ai.html`
- `templates/admin/ai/inventory.html`
- `templates/admin/ai/nav.html`
- `templates/admin/ai/revenue-forecast.html`
- `templates/customer/ai/chat.html`
- `templates/customer/ai/face_attendance.html`

Sửa:
- `customers/models.py`
- `customers/ai_views.py`
- `customers/views.py`
- `customers/rbac.py`
- `customers/context_processors.py`
- `restaurant_system/settings.py`
- `restaurant_system/urls.py`
- `static/admin/js/main.js`
- `templates/index.html`
- `templates/customer/base.html`
- `requirements.txt`

Artifact/log được tạo: `ai_models/` (dataset/model/RAG/evaluation versions + manifest), `ai_verification/`, `qa_browser/results.json`, các `ai-*.log`. Các version cũ được giữ.

Hướng dẫn chạy/demo/calibration và giới hạn: [AI_PHASE.md](AI_PHASE.md). Không triển khai GIS/GPS/Haversine/Leaflet.


## Cập nhật hoàn thiện 14/10/2026

Xem [FINAL_REPORT.md](FINAL_REPORT.md) và [FINAL_DEMO.md](FINAL_DEMO.md): redesign, chatbot, FaceID UX, GIS và live Edge E2E. Hạn chế browser trong báo cáo cũ là lịch sử; live HTTP đã kiểm tra được ở giai đoạn này. Webcam/GPS thật, enrollment và threshold calibration vẫn chưa được kiểm chứng. Các metric AI cũ giữ nguyên provenance.
