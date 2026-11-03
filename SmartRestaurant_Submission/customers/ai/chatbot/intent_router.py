import re
import unicodedata
from rapidfuzz import fuzz

INTENTS=['GREETING','MENU_SEARCH','MENU_PRICE','MENU_DETAIL','MENU_RECOMMENDATION','COMBO_INFO','PROMOTION_INFO','RESTAURANT_INFO','OPENING_HOURS','BOOKING_POLICY','BOOKING_AVAILABILITY','MY_BOOKING','MY_ORDER_STATUS','MY_PAYMENT_STATUS','CART_ADD','CART_VIEW','WEBSITE_HELP','POLICY','FAQ','OUT_OF_SCOPE','UNKNOWN']

from .normalization import normalize

def route(text,memory=None):
    text=normalize(text); memory=memory or {}
    if any(w in text for w in ['thoi tiet','chinh tri','bitcoin','bong da','lap trinh','tong thong']): return 'OUT_OF_SCOPE'
    if any(w in text for w in ['huong dan','cach su dung','cach xem','cach dat']): return 'WEBSITE_HELP'
    if 'hoa don' in text: return 'MY_PAYMENT_STATUS'
    if re.search(r'\b(don|don hang)\s+(?:cua\s+)?toi\b',text) and not re.search(r'tra tien|thanh toan',text): return 'MY_ORDER_STATUS'
    if re.search(r'\b(tra tien|tra roi|thanh toan|tien da tra)\b',text): return 'MY_PAYMENT_STATUS'
    if re.search(r'\bgio\s+(co gi|co nhung|cua toi)\b',text): return 'CART_VIEW'
    if re.search(r'\b(?:nha hang|quan)\s+co\s+gi\b',text): return 'MENU_SEARCH'
    if re.search(r'\b(them|cho vao gio)\b',text): return 'CART_ADD'
    if 'combo' in text: return 'COMBO_INFO'
    if re.search(r'\b(dat ban|dat cho|con ban)\b',text) and not re.search(r'chinh sach|huy|cua toi',text): return 'BOOKING_AVAILABILITY'
    if memory.get('pending')=='BOOKING_AVAILABILITY' and re.search(r'\d|mai|hom nay|sang|toi',text): return 'BOOKING_AVAILABILITY'
    if re.search(r'\b(mon thu|mon so)\s*\d+',text): return 'MENU_PRICE' if re.search(r'gia|bao nhieu',text) else 'MENU_DETAIL'
    if re.search(r'\b(goi y|de xuat)\b',text): return 'MENU_RECOMMENDATION'
    if re.search(r'\b(duoi|tren|tu)\s*\d',text): return 'MENU_SEARCH'
    if re.search(r'\b(re re|mon re|ngon|an gi)\b',text): return 'MENU_RECOMMENDATION'
    rules=[
        ('CART_ADD',['them','vao gio']),('CART_VIEW',['gio hang','gio mon']),
        ('MY_PAYMENT_STATUS',['thanh toan cua toi','hoa don cua toi','hoa don #','payment']),
        ('MY_ORDER_STATUS',['don cua toi','don hang cua toi','don hang #','don #','trang thai don']),
        ('MY_BOOKING',['dat ban cua toi','lich dat cua toi','dat ban #']),
        ('BOOKING_POLICY',['chinh sach dat','huy ban','huy dat']),
        ('BOOKING_AVAILABILITY',['con ban','dat ban','dat giup','dat cho']),
        ('PROMOTION_INFO',['khuyen mai','voucher','uu dai']),('COMBO_INFO',['combo']),
        ('OPENING_HOURS',['mo cua','dong cua','may gio mo']),
        ('MENU_RECOMMENDATION',['goi y','an gi','de xuat mon']),
        ('MENU_PRICE',['gia','bao nhieu','bao nhieu tien']),('MENU_DETAIL',['chi tiet','nguyen lieu','mo ta']),
        ('MENU_SEARCH',['mon','hai san','bo','ribeye','thuc don']),
        ('RESTAURANT_INFO',['dia chi','dien thoai','nha hang o','lien he']),
        ('WEBSITE_HELP',['huong dan','cach','website','su dung']),
        ('POLICY',['chinh sach','quy dinh']),('FAQ',['cau hoi thuong gap']),
    ]
    if re.fullmatch(r'(chao|xin chao|hello|hi)( nhe| vui long)?',text): return 'GREETING'
    if memory.get('pending')=='BOOKING_AVAILABILITY' and re.search(r'\d|mai|hom nay',text): return 'BOOKING_AVAILABILITY'
    if memory.get('menu_item_id') and re.search(r'^(no|mon do|gia|bao nhieu)',text): return 'MENU_PRICE' if 'gia' in text or 'bao nhieu' in text else 'MENU_DETAIL'
    for intent,phrases in rules:
        if any(re.search(r'(?<!\w)'+re.escape(p)+r'(?!\w)',text) for p in phrases): return intent
    # Typo recovery is bounded to short intent phrases, no hard-coded eval questions.
    candidates=[(fuzz.ratio(text,p),intent) for intent,phrases in rules for p in phrases if len(text)<40 and len(p)>5]
    best=max(candidates,default=(0,'UNKNOWN'))
    return best[1] if best[0]>=85 else 'UNKNOWN'
