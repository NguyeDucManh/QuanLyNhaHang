import re
from datetime import date,time,timedelta
from django.utils import timezone
from django.core.exceptions import ValidationError
from .intent_router import normalize

def booking_entities(text,memory):
    value=normalize(text); entities=dict(memory.get('booking',{}))
    today=timezone.localdate()
    if 'mai' in value: entities['date']=(today+timedelta(days=1)).isoformat()
    elif 'hom nay' in value: entities['date']=today.isoformat()
    iso=re.search(r'\b(\d{4}-\d{2}-\d{2})\b',value)
    if iso: entities['date']=date.fromisoformat(iso[1]).isoformat()
    local=re.search(r'\b(\d{1,2})\s*(?:/|-|thang)\s*(\d{1,2})(?:\s*(?:/|-|nam)\s*(\d{4}))?\b',value) if not iso else None
    if local:
        try: entities['date']=date(int(local[3] or today.year),int(local[2]),int(local[1])).isoformat()
        except ValueError: raise ValidationError('Ngày đặt bàn không hợp lệ; nhập ngày/tháng/năm.')
    guests=re.search(r'\b(\d{1,2})\s*(nguoi|khach)\b',value)
    if guests: entities['guests']=int(guests[1])
    elif re.fullmatch(r'\d{1,2}',value) and not entities.get('guests') and memory.get('pending')=='BOOKING_AVAILABILITY': entities['guests']=int(value)
    clock=re.search(r'\b(\d{1,2})(?::(\d{2})|\s*(?:h|gio)(\d{2})?)\b',value)
    if clock:
        hour=int(clock[1]); minute=int(clock[2] or clock[3] or 0)
        entities['hour_hint']=hour
        if 'toi' in value and hour<12: hour+=12
        # "7h" without AM/PM is ambiguous; ask instead of choosing.
        if hour<12 and not any(w in value for w in ['sang','toi','chieu','trua']) and ':' not in clock[0]:
            entities.pop('time',None); entities['ambiguous_time']=True
        else:
            entities['time']=time(hour,minute).isoformat(); entities.pop('ambiguous_time',None)
    elif entities.get('ambiguous_time') and value in ['toi','buoi toi','sang','buoi sang']:
        hour=entities['hour_hint']; hour=hour+12 if 'toi' in value and hour<12 else hour
        entities['time']=time(hour).isoformat(); entities.pop('ambiguous_time',None)
    return entities

def booking_followup(entities,memory):
    if entities.get('ambiguous_time'): return f'Bạn muốn đặt lúc {entities.get("hour_hint",7)} giờ sáng hay tối?'
    missing=[key for key in ['guests','date','time'] if key not in entities]
    memory['awaiting_slot']='guests' if 'guests' in missing else 'date' if 'date' in missing else 'time' if 'time' in missing else None
    if len(missing)==3: return 'Bạn muốn đặt ngày nào, lúc mấy giờ và cho bao nhiêu người?'
    known=[]
    if 'date' in entities: known.append('Ngày '+date.fromisoformat(entities['date']).strftime('%d/%m'))
    if 'guests' in entities: known.append(f'{entities["guests"]} người')
    if 'time' in entities: known.append('lúc '+entities['time'][:5])
    labels={'date':'ngày nào','time':'lúc mấy giờ','guests':'cho bao nhiêu người'}
    return ', '.join(known)+'. Bạn muốn đặt '+' và '.join(labels[key] for key in ['date','time','guests'] if key in missing)+'?'
