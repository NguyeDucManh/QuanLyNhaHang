from datetime import datetime
import re
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Booking, MenuItem, Area, RestaurantTable


class CustomerRegistrationForm(UserCreationForm):
    first_name = forms.CharField(label="Họ và tên", max_length=100)
    email = forms.EmailField(label="Email")

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("first_name", "username", "email", "password1", "password2")


class BookingForm(forms.ModelForm):
    preferred_area = forms.ModelChoiceField(queryset=Area.objects.filter(is_active=True).order_by('name'),required=False,label='Khu vực ưu tiên',empty_label='Bất kỳ khu vực phù hợp')
    class Meta:
        model = Booking
        fields = ("name", "phone", "date", "time", "guests", "note")
        widgets = {
            "date": forms.DateInput(attrs={"type": "date"}),
            "time": forms.TimeInput(attrs={"type": "time"}),
            "guests": forms.NumberInput(attrs={"min": 1, "max": 20}),
            "note": forms.Textarea(attrs={"rows": 3, "placeholder": "Dị ứng thực phẩm, dịp đặc biệt…"}),
        }

    def clean_phone(self):
        phone = self.cleaned_data["phone"].strip()
        if not re.fullmatch(r"\+?[0-9\s().-]{9,20}", phone):
            raise forms.ValidationError("Vui lòng nhập số điện thoại hợp lệ.")
        return phone

    def clean_guests(self):
        guests = self.cleaned_data["guests"]
        if not 1 <= guests <= 20:
            raise forms.ValidationError("Vui lòng chọn từ 1 đến 20 khách.")
        return guests

    def clean(self):
        data = super().clean()
        if data.get("date") and data.get("time"):
            from .booking_service import booking_window
            booking_window(data["date"], data["time"])
        return data



class MenuItemForm(forms.ModelForm):
    image = forms.ChoiceField(label="Ảnh hiện có")

    class Meta:
        model = MenuItem
        fields = ('name', 'category', 'price', 'image', 'description', 'is_available')
        widgets = {'description': forms.Textarea(attrs={'rows': 4}), 'price': forms.NumberInput(attrs={'min': '0', 'step': '0.01'})}

    def __init__(self, *args, **kwargs):
        from pathlib import Path
        from django.conf import settings
        super().__init__(*args, **kwargs)
        self.fields['image'].choices = [('', 'Chọn ảnh')] + [
            ('Image/' + p.name, p.name) for p in sorted((settings.BASE_DIR / 'static' / 'Image').iterdir())
            if p.is_file() and p.suffix.lower() in ('.jpg', '.jpeg', '.png', '.webp')]

    def clean_price(self):
        price = self.cleaned_data['price']
        if price is not None and price < 0:
            raise forms.ValidationError("Giá không được âm.")
        return price



class AccountRoleForm(forms.Form):
    from .rbac import ROLES
    role = forms.ChoiceField(label="Vai trò", choices=[(r, r) for r in ROLES])
    is_active = forms.BooleanField(label="Tài khoản đang hoạt động", required=False)


class AreaForm(forms.ModelForm):
    class Meta:
        model = Area
        fields = ('name', 'description', 'is_active')
        widgets = {'description': forms.Textarea(attrs={'rows': 3})}


class RestaurantTableForm(forms.ModelForm):
    class Meta:
        model = RestaurantTable
        fields = ('area', 'code', 'capacity', 'status', 'is_active')
        widgets = {'capacity': forms.NumberInput(attrs={'min': 1})}
