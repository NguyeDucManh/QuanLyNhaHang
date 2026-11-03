"""HTML text presentation only; persisted data, URLs, JSON and hidden fields stay intact."""
from html.parser import HTMLParser
from html import escape
from .operational_labels import operational_text

class OperationalHTML(HTMLParser):
    def __init__(self):super().__init__(convert_charrefs=False);self.parts=[];self.raw=0
    def handle_starttag(self,tag,attrs):
        if tag in {'script','style'}:self.raw+=1
        values=dict(attrs)
        updated=[]
        for name,value in attrs:
            if value is not None and name in {'title','alt','aria-label'}:value=operational_text(value)
            if tag=='input' and name=='value' and values.get('type','text') in {'text','email','tel'}:
                clean=operational_text(value)
                value='' if clean in {'Chưa cập nhật','Hồ sơ cần xác nhận'} else clean
            updated.append(name if value is None else f'{name}="{escape(value,quote=True)}"')
        self.parts.append('<'+tag+(' '+' '.join(updated) if updated else '')+'>')
    def handle_startendtag(self,tag,attrs):
        self.handle_starttag(tag,attrs);self.parts[-1]=self.parts[-1][:-1]+' />'
        if tag in {'script','style'}:self.raw=max(0,self.raw-1)
    def handle_endtag(self,tag):
        self.parts.append('</'+tag+'>')
        if tag in {'script','style'}:self.raw=max(0,self.raw-1)
    def handle_data(self,data):self.parts.append(data if self.raw else operational_text(data))
    def handle_entityref(self,name):self.parts.append('&'+name+';')
    def handle_charref(self,name):self.parts.append('&#'+name+';')
    def handle_decl(self,decl):self.parts.append('<!'+decl+'>')
    def handle_comment(self,data):self.parts.append('<!--'+data+'-->')

class OperationalLabelsMiddleware:
    def __init__(self,get_response):self.get_response=get_response
    def __call__(self,request):
        response=self.get_response(request)
        if not response.streaming and response.get('Content-Type','').startswith('text/html'):
            parser=OperationalHTML();parser.feed(response.content.decode(response.charset));parser.close()
            response.content=''.join(parser.parts).encode(response.charset)
            if response.has_header('Content-Length'):response['Content-Length']=len(response.content)
        return response
