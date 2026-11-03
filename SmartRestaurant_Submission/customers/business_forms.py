import uuid
from decimal import Decimal
from django import forms
from django.forms import formset_factory
from django.contrib.auth.models import User
from django.utils import timezone
from .models import Category,Supplier,Ingredient,RecipeIngredient,Order,MenuItem,RestaurantTable,Payment


class CategoryForm(forms.ModelForm):
    class Meta:
        model=Category
        fields=('name','slug','is_active')


class SupplierForm(forms.ModelForm):
    class Meta:
        model=Supplier
        fields=('code','name','contact_name','phone','email','address','is_active')
        widgets={'address':forms.Textarea(attrs={'rows':3})}


class IngredientForm(forms.ModelForm):
    minimum_stock=forms.DecimalField(label='Tồn tối thiểu',max_digits=14,decimal_places=3,min_value=0)
    class Meta:
        model=Ingredient
        fields=('code','name','unit','minimum_stock','is_active')


class RecipeForm(forms.ModelForm):
    class Meta:
        model=RecipeIngredient
        fields=('menu_item','ingredient','quantity_required')


class RequestForm(forms.Form):
    request_key=forms.UUIDField(widget=forms.HiddenInput)

    def __init__(self,*args,**kwargs):
        super().__init__(*args,**kwargs)
        if not self.is_bound:
            self.fields['request_key'].initial=uuid.uuid4()


class OrderForm(RequestForm):
    customer=forms.ModelChoiceField(label='Khách hàng (không bắt buộc)',queryset=User.objects.filter(is_active=True),required=False)
    order_type=forms.ChoiceField(label='Hình thức',choices=Order.Type.choices)
    table=forms.ModelChoiceField(label='Bàn (đơn tại bàn)',queryset=RestaurantTable.objects.filter(is_active=True,area__is_active=True).exclude(status='MAINTENANCE'),required=False)
    note=forms.CharField(label='Ghi chú',widget=forms.Textarea(attrs={'rows':2}),required=False,max_length=1000)


class OrderLineForm(forms.Form):
    from .models import Topping
    toppings=forms.ModelMultipleChoiceField(label='Topping (backend kiểm tra phù hợp món)',queryset=Topping.objects.filter(is_available=True),required=False)
    menu_item=forms.ModelChoiceField(label='Món',empty_label='— Chọn món —',queryset=MenuItem.objects.filter(is_available=True,category__is_active=True,price__isnull=False))
    quantity=forms.IntegerField(label='Số lượng',min_value=1,max_value=1000)
    note=forms.CharField(label='Ghi chú món',required=False,max_length=250)


class DocumentForm(RequestForm):
    date=forms.DateField(label='Ngày',initial=timezone.localdate,widget=forms.DateInput(attrs={'type':'date'},format='%Y-%m-%d'))
    note=forms.CharField(label='Ghi chú',required=False,widget=forms.Textarea(attrs={'rows':2}),max_length=1000)


class ReceiptForm(DocumentForm):
    supplier=forms.ModelChoiceField(label='Nhà cung cấp',queryset=Supplier.objects.filter(is_active=True))


class IssueForm(DocumentForm):
    reason=forms.CharField(label='Lý do xuất kho',max_length=250)


class StockLineForm(forms.Form):
    ingredient=forms.ModelChoiceField(label='Nguyên liệu',queryset=Ingredient.objects.filter(is_active=True))
    quantity=forms.DecimalField(label='Số lượng (đơn vị của nguyên liệu)',max_digits=12,decimal_places=3,min_value=Decimal('0.001'))


class ReceiptLineForm(StockLineForm):
    unit_price=forms.DecimalField(label='Đơn giá',max_digits=12,decimal_places=2,min_value=0,initial=0)


class PaymentForm(RequestForm):
    payment_method=forms.ChoiceField(label='Phương thức',choices=Payment.Method.choices)
    transaction_reference=forms.CharField(label='Mã giao dịch chuyển khoản',required=False,max_length=100)


class CustomerPaymentForm(RequestForm):
    payment_method=forms.ChoiceField(label='Phương thức thanh toán',choices=[('CASH','Tiền mặt'),('BANK_TRANSFER','Chuyển khoản QR DEMO')])


OrderLines=formset_factory(OrderLineForm,extra=1,min_num=1,validate_min=True,max_num=100,validate_max=True,absolute_max=100)
ReceiptLines=formset_factory(ReceiptLineForm,extra=1,min_num=1,validate_min=True,max_num=100,validate_max=True,absolute_max=100)
IssueLines=formset_factory(StockLineForm,extra=1,min_num=1,validate_min=True,max_num=100,validate_max=True,absolute_max=100)
