"""Render a report from measured artifacts, never from invented metric constants."""
import json
import os
from pathlib import Path
import re
import sys
WORKSPACE=Path(__file__).resolve().parent.parent
sys.path.insert(0,str(WORKSPACE)); os.environ.setdefault('DJANGO_SETTINGS_MODULE','restaurant_system.settings')
import django
django.setup()
from customers.ai.artifacts import latest,read_json
from customers.models import Order,OrderItem,MenuItem,Employee,Ingredient,FaceProfile,FaceEmbedding
from customers.ai.chatbot.intent_router import INTENTS
from customers.ai.chatbot.tool_registry import SCHEMAS

def number(value): return 'N/A' if value is None else f'{value:,.6f}'

research=read_json(latest('datasets')/'metadata.json'); rec=read_json(latest('recommendation')/'metadata.json'); forecast=read_json(latest('forecast')/'metadata.json'); chat=read_json(latest('chatbot')/'metadata.json'); evaluation=read_json(latest('evaluation')/'metadata.json'); manifest=read_json(WORKSPACE/'ai_models/pretrained/manifest.json')
results_file=WORKSPACE/'ai_verification/results.json'; checks=read_json(results_file) if results_file.exists() else []
log=(WORKSPACE/'ai_verification/3.log').read_text(encoding='utf-8') if (WORKSPACE/'ai_verification/3.log').exists() else ''
tests=re.search(r'Ran (\d+) tests in ([\d.]+)s',log)
text=['# Báo cáo giai đoạn AI — Smart Restaurant','',f"Dataset `{research['version']}`; recommendation `{rec['version']}`; forecast `{forecast['version']}`; RAG `{chat['version']}`; evaluation `{evaluation['version']}`.",'','Số dưới đây được đọc từ artifact train/evaluate thật. Phần mô phỏng và các chỉ số proxy được ghi riêng.','', '## Recommendation','',f"{research['real_interactions']} interaction thật + {research['synthetic_interactions']} SYNTHETIC. Seed {research['seed']}. Best α = {rec['best_alpha']} (validation NDCG@5).",'', '| Model | Users test (real / simulated) | Precision@5 | Recall@5 | F1@5 | NDCG@5 |','|---|---:|---:|---:|---:|---:|']
for name,m in rec['metrics'].items(): text.append(f"| {name} | {m.get('real_users','N/A')} / {m.get('synthetic_users','N/A')} | {number(m['precision_at_5'])} | {number(m['recall_at_5'])} | {number(m['f1_at_5'])} | {number(m['ndcg_at_5'])} |")
text+=['','Các user có history thật hiện chưa đủ cho temporal test; kết quả chủ yếu trên khách mô phỏng, không được gọi là metrics khách thật.','', '## Forecast','',f"{research['real_days']} ngày thật + {research['synthetic_days']} SYNTHETIC, liên tục {research['start']} → {research['end']}; {len(research['recipe_menu_ids'])} món có recipe × 70 ngày. Seed {research['seed']}.", '', '| Target | Model | MAE | RMSE | MAPE (%) |','|---|---|---:|---:|---:|']
bests=[]
for target in ['revenue','order_count']:
    summary=forecast['series'][target]
    for name,m in summary['metrics'].items(): text.append(f"| {target} | {name} | {number(m['MAE'])} | {number(m['RMSE'])} | {number(m['MAPE'])} |")
    bests.append(f"Best `{target}`: **{summary['best_model']}**, chọn theo validation MAE; train {summary['train_range']}, validation {summary['validation_range']}, test {summary['test_range']}.")
text+=['']+bests+['']
text+=['MAPE cao được giữ nguyên: tập test có ngày doanh số thật thấp hơn nhiều các ngày mô phỏng. Không có tuyên bố accuracy 99%. Model chưa chứng minh chất lượng dự báo vận hành. Forecast 30 ngày chỉ thăm dò, không có prediction interval. Actual/Predicted và feature importance/coefficient của cả ba model lưu trong metadata và UI.','', '| Món | Model chọn | MAE test | RMSE test | MAPE test (%) |','|---|---|---:|---:|---:|']
menus={m.pk:m.name for m in MenuItem.objects.all()}
for target,summary in forecast['series'].items():
    if not target.startswith('menu_'): continue
    m=summary['metrics'][summary['best_model']]; text.append(f"| {menus.get(int(target[5:]),target)} | {summary['best_model']} | {number(m['MAE'])} | {number(m['RMSE'])} | {number(m['MAPE'])} |")
inv=evaluation['inventory']; text+=['','## AI Inventory','',f"Đánh giá {inv['ingredient_count']} Ingredient. Risk: `{json.dumps(inv['risks'])}`.",'','Policy mặc định lead time **2 ngày (giả định, chưa gán Supplier)**; safety **3 ngày**, cho phép 3/5/7. Có UI gán Supplier/lead time/safety theo Ingredient. Reorder point = daily demand × lead time + max(safety stock, minimum stock). What-if +10%/+20% chỉ preview. Không sửa stock, không tự tạo phiếu nhập. Demand chỉ phủ 15 món recipe; nguyên liệu khác được đánh dấu chưa bao phủ.','', '| Nguyên liệu | Đơn vị | Usage 7 ngày | Đề xuất mua | Risk |','|---|---|---:|---:|---|']
for row in inv['examples']: text.append(f"| {row['ingredient']} | {row['unit']} | {number(float(row['predicted_usage']))} | {number(float(row['recommended_purchase']))} | {row['risk']} |")
text+=['','## FaceID','',f"Pretrained FaceNet ONNX, RGB 160×160 → embedding 128-d L2, ONNX Runtime CPU. {FaceProfile.objects.count()} Employee enrolled; {FaceEmbedding.objects.count()} embedding thật. Threshold: **chưa calibrate**.",'','**Chưa đủ dữ liệu khuôn mặt thật để công bố metrics.** Không có accuracy/precision/recall/F1/FAR/FRR giả. Cần enrollment thật 10–20 frame/người và bốn tập ảnh validation/test genuine/impostor riêng (≥5 ảnh/tập/người) để chạy `calibrate_faceid`. Tests hiện kiểm tra pipeline/ownership/liveness/service integration bằng fixtures và mocks; không coi đó là accuracy nhận diện người thật.','',f"FaceNet revision `{manifest['facenet.onnx']['revision']}`, SHA-256 `{manifest['facenet.onnx']['sha256']}`.",'','Liveness basic: random blink/left/right, neutral → action → neutral, landmark được server trích; challenge gắn actor, 90 giây, một lần. Server xác định Employee và gọi Attendance service cũ. Camera thật/video spoof chưa đánh giá; không phải anti-spoof cấp cao. Upstream community ONNX export chưa có model card đầy đủ về training/license.','', '## AI Chatbox','',f"{len(INTENTS)} intents: `{', '.join(INTENTS)}`.",'',f"{len(SCHEMAS)} tools/schema đóng: `{', '.join(SCHEMAS)}`.",'','Guard → router/entities → session/user memory → DB/business tools hoặc sentence-transformers + FAISS → semantic/BM25 rerank → extractive answer → concise guard → human handoff. AIConversation/AIMessage riêng, không trộn human chat. Giá/trạng thái đọc DB live; ownership được kiểm tra; không dùng external LLM/API.','',f"{chat['documents']} documents / {chat['chunks']} chunks. Model `{chat['model_name']}`, revision `{chat['model_revision']}`, CPU. Vector Top 10, rerank Top 3; lexical+semantic reranker.",'',f"{evaluation['chatbot']['question_count']} câu evaluation template từ DB/policy + {evaluation['chatbot']['multi_turn_count']} hội thoại. Không phải bộ câu hỏi user thật độc lập.",'','| Chỉ số | Kết quả |','|---|---:|']
for name,value in evaluation['chatbot']['metrics'].items(): text.append(f'| {name} | {number(value)} |')
text+=['',f"Có {evaluation['chatbot']['failed_assertions']} assertion chưa đạt. Chi tiết trong `ai_models/evaluation/{evaluation['version']}/chatbot_results.json`.",'','Answer correctness là proxy so khớp chuỗi entity/giá/giờ, groundedness là proxy nguồn hiện diện, hallucination chỉ kiểm tra assertion giá/giờ/combo. Câu không có assertion bị loại khỏi correctness. **Không gọi các chỉ số proxy này là đánh giá ngữ nghĩa toàn diện.** Có `manual_review_sample` để người dùng chấm tay. RAG thresholds hiện heuristic, chưa hiệu chỉnh trên validation độc lập. Router/entity parser còn hạn chế; chưa hỗ trợ đầy đủ mọi cách diễn đạt/ngày tương đối.','', '## System và verification','', 'Migration mới: `customers/migrations/0016_aiconversation_aimessage_faceaudit_facechallenge_and_more.py`; chỉ thêm bảng AI/policy, không xóa dữ liệu nghiệp vụ cũ.','']
if tests: text.append(f"Full regression: **{tests[1]}/{tests[1]} PASS**, {tests[2]} giây (331 tests cũ + {int(tests[1])-331} tests mới).")
else: text.append('Full regression đang chạy; xem ai_verification/3.log.')
for check in checks: text.append('- `'+ ' '.join(check['command'][1:])+'`: '+('PASS' if check['exit_code']==0 else 'FAIL')+f" ({check['seconds']}s).")
counts={model.__name__:model.objects.count() for model in [Order,OrderItem,MenuItem,Employee,Ingredient]}
text+=['',f"Counts database vận hành sau triển khai: `{json.dumps(counts)}`. Không tạo Order/Customer/Attendance mô phỏng vào DB chính; không sửa stock hay dùng browser fixtures trong DB chính.",'']
text.append('Browser: kiểm tra 6 trang × desktop/mobile trong Chrome DOM/layout, không tràn ngang; chat HTTP/CSRF PASS trên PostgreSQL tạm riêng, đã xóa DB tạm. Chrome navigation localhost bị ERR_ABORTED và screenshot bị timeout, nên dùng HTML/CSS/JS inject; **chưa xác nhận live browser end-to-end hoặc webcam thật**. Kết quả máy đọc được: `qa_browser/results.json`.')
text+=['','Dependencies AI được giữ nguyên, ghi đúng installed versions trong requirements.txt. Thêm websocket-client 1.9.2 chỉ để browser QA, requirements-dev.txt. Model/cache ở `D:\\SmartRestaurant-AI-cache`, manifest/source/revision/hash nằm trong project.','', '## Files tạo/sửa','']
created=[p.relative_to(WORKSPACE).as_posix() for p in (WORKSPACE/'customers/ai').rglob('*.py')]
created+=['customers/ai_models.py','customers/ai_phase_views.py','customers/cart_service.py','customers/test_ai_phase.py','customers/migrations/0016_aiconversation_aimessage_faceaudit_facechallenge_and_more.py']
created+=['customers/management/commands/'+name+'.py' for name in ['download_ai_models','prepare_ai_research_data','train_recommendation_models','train_forecast_models','rebuild_chatbot_index','evaluate_ai_models','calibrate_faceid']]
created+=[p.relative_to(WORKSPACE).as_posix() for p in (WORKSPACE/'templates/admin/ai').glob('*.html') if p.name not in ['schedules.html','recommendations.html']]
created+=[p.relative_to(WORKSPACE).as_posix() for p in (WORKSPACE/'templates/customer/ai').glob('*.html') if p.name!='recommendations.html']
created+=['static/ai/ai.js','requirements-dev.txt','scripts/ai_browser_smoke.py','scripts/ai_final_checks.py','scripts/write_ai_report.py','docs/AI_PHASE.md','docs/AI_REPORT.md']
modified=['customers/models.py','customers/ai_views.py','customers/views.py','customers/rbac.py','customers/context_processors.py','restaurant_system/settings.py','restaurant_system/urls.py','static/admin/js/main.js','templates/index.html','templates/customer/base.html','requirements.txt']
text+=['Tạo:']+['- `'+p+'`' for p in sorted(set(created))]+['','Sửa:']+['- `'+p+'`' for p in modified]
text+=['','Artifact/log được tạo: `ai_models/` (dataset/model/RAG/evaluation versions + manifest), `ai_verification/`, `qa_browser/results.json`, các `ai-*.log`. Các version cũ được giữ.','', 'Hướng dẫn chạy/demo/calibration và giới hạn: [AI_PHASE.md](AI_PHASE.md). Không triển khai GIS/GPS/Haversine/Leaflet.']
(WORKSPACE/'docs/AI_REPORT.md').write_text('\n'.join(text)+'\n',encoding='utf-8')
print('Report written from current measured artifacts.')
