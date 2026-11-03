"""Vietnamese accent-insensitive, conservative teencode and money parsing."""
import re
import unicodedata
from decimal import Decimal
ALIASES={'ko':'khong','kh':'khong','hong':'khong','k':'khong','gid':'gi','nhiu':'bao nhieu','bn':'bao nhieu','ng':'nguoi','t':'toi','tui':'toi','hs':'hai san','dc':'duoc','j':'gi','hem':'khong'}
def normalize(text):
    value=unicodedata.normalize('NFD',str(text).lower().replace('đ','d'))
    value=''.join(c for c in value if unicodedata.category(c)!='Mn')
    value=re.sub(r'(\d)\s+(k|tr)\b',r'\1\2',value)
    value=re.sub(r'\b[a-z]+\b',lambda m:ALIASES.get(m[0],m[0]),value)
    return re.sub(r'\s+',' ',value).strip()
def amount(raw,unit=None):
    raw=re.sub(r'\s+','',raw.strip()).replace(',','.')
    mixed=re.fullmatch(r'(\d+)tr(\d{1,3})',raw)
    if mixed: return int(mixed[1])*1000000+int(mixed[2])*10**(6-len(mixed[2]))
    match=re.fullmatch(r'(\d+(?:\.\d+)?)\s*(trieu|tr|k|nghin|ngan|d|dong)?',raw)
    if not match: return None
    suffix=match[2] or unit; scale=1000000 if suffix in ['tr','trieu'] else 1000 if suffix in ['k','nghin','ngan'] else 1
    return int(Decimal(match[1])*scale)
def price_entities(text):
    value=normalize(text); money=r'\d+(?:[.,]\d+)?\s*(?:tr\d{1,3}|trieu|tr|k|nghin|ngan|dong|d)?'; result={}
    interval=re.search(r'(?:tu|khoang)\s*('+money+r')\s*(?:den|toi|[-–])\s*('+money+r')',value)
    if interval:
        suffix=re.search(r'(trieu|tr|k|nghin|ngan)\s*$',interval[2]); result={'min_price':amount(interval[1],suffix[1] if suffix else None),'max_price':amount(interval[2])}
    else:
        for key,pattern in [('max_price',r'(?:duoi|toi da|khong qua|tam|ngan sach)\s*('+money+r')'),('min_price',r'(?:tren|it nhat|tu)\s*('+money+r')')]:
            found=re.search(pattern,value)
            if found: result[key]=amount(found[1])
    return {key:value for key,value in result.items() if value is not None}
