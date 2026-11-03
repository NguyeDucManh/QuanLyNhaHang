import re
from .intent_router import normalize

NO_DATA='Tôi chưa có đủ thông tin trong dữ liệu nhà hàng để trả lời câu hỏi này.'
OUT_OF_SCOPE='Tôi chỉ hỗ trợ các thông tin liên quan đến nhà hàng và hệ thống.'
REFUSAL='Tôi không thể cung cấp bí mật hệ thống hoặc dữ liệu riêng của người khác.'

def blocked(text):
    value=normalize(text)
    return any(phrase in value for phrase in ['secret_key','secret key','database password','db_password','mat khau','system prompt','hidden context','payroll','bang luong','embedding','bo qua huong dan','ignore previous','nguoi khac','khach khac','system:','<script'])

def concise(answer):
    # Tools already produce precise responses; trim only excessive grounded excerpts.
    answer=str(answer).strip()
    sentences=re.split(r'(?<=[.!?])\s+(?!\d+[.)])',answer)
    if re.search(r'\b\d+\. ',answer): return answer[:900]
    return ' '.join(sentences[:4])[:900]
