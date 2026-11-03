from django.core.exceptions import ValidationError
from .intent_router import route
from .answer_guard import blocked,concise,REFUSAL,NO_DATA,OUT_OF_SCOPE
from .tool_registry import TOOLS,call

def respond(question,memory,request):
    if not isinstance(question,str) or not 1<=len(question.strip())<=2000: raise ValidationError('Tin nhắn phải từ 1 đến 2000 ký tự.')
    if blocked(question): result={'answer':REFUSAL,'intent':'REFUSAL','tool':'input_guard','sources':[]}
    else:
        intent=route(question,memory)
        if intent=='GREETING': result={'answer':'Bạn cần tìm món, kiểm tra đặt bàn hay xem đơn hàng?','tool':'','sources':[]}
        elif intent=='OUT_OF_SCOPE': result={'answer':OUT_OF_SCOPE,'tool':'input_guard','sources':[]}
        elif intent in TOOLS: result=call(intent,question,memory,request)
        else:
            from .rag_service import answer
            result=answer(question,intent)
        result['intent']=intent
    result['answer']=concise(result['answer'])
    if result['intent'] in ['MENU_SEARCH','MENU_RECOMMENDATION']:
        from .normalization import price_entities
        result['entities']=price_entities(question)
    elif result['intent']=='BOOKING_AVAILABILITY':
        result['entities']={key:memory.get('booking',{}).get(key) for key in ['date','time','guests'] if key in memory.get('booking',{})}
    result['handoff']=result['answer'] in [NO_DATA,OUT_OF_SCOPE,REFUSAL] or result['intent']=='UNKNOWN'
    return result
