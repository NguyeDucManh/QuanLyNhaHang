from datetime import timedelta
from django import forms
from django.utils import timezone

class GAForm(forms.Form):
    start_date=forms.DateField(label='Ngày bắt đầu',widget=forms.DateInput(attrs={'type':'date'}))
    end_date=forms.DateField(label='Ngày kết thúc',widget=forms.DateInput(attrs={'type':'date'}))
    population_size=forms.IntegerField(label='Kích thước quần thể',min_value=4,max_value=200,initial=50)
    generations=forms.IntegerField(label='Số thế hệ',min_value=1,max_value=300,initial=80)
    mutation_rate=forms.FloatField(label='Tỷ lệ đột biến',min_value=0,max_value=1,initial=.08)
    crossover_rate=forms.FloatField(label='Tỷ lệ lai ghép',min_value=0,max_value=1,initial=.8)
    random_seed=forms.IntegerField(label='Giá trị khởi tạo ngẫu nhiên',min_value=0,max_value=2**32-1,initial=42)
    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        self.fields['start_date'].initial=timezone.localdate()+timedelta(days=1)
        self.fields['end_date'].initial=timezone.localdate()+timedelta(days=7)
    def clean(self):
        data=super().clean();start=data.get('start_date');end=data.get('end_date')
        if start and end and (start<timezone.localdate() or end<start or (end-start).days>13):raise forms.ValidationError('Chọn từ hôm nay, tối đa 14 ngày.')
        return data
