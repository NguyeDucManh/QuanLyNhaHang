from django.contrib import admin
from .models import Booking


@admin.register(Booking)
class BookingAdmin(admin.ModelAdmin):
    list_display = ('id', 'name', 'phone', 'date', 'start_time', 'end_time', 'guests', 'table', 'status')
    search_fields = ('name', 'phone')
    list_filter = ('date', 'status')

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False




from django.utils.html import format_html
from django.templatetags.static import static
from .models import Category, MenuItem
from .forms import MenuItemForm


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'slug', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('name',)
    prepopulated_fields = {'slug': ('name',)}

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(MenuItem)
class MenuItemAdmin(admin.ModelAdmin):
    form = MenuItemForm
    list_display = ('id', 'photo', 'name', 'category', 'price', 'is_available')
    list_filter = ('category', 'is_available')
    search_fields = ('name',)
    actions = ['disable_items']

    @admin.display(description='Ảnh')
    def photo(self, obj):
        return format_html('<img src="{}" alt="{}" width="80">', static(obj.image), obj.name)

    @admin.action(description='Ngừng phục vụ các món đã chọn')
    def disable_items(self, request, queryset):
        from django.utils import timezone
        queryset.update(is_available=False, updated_at=timezone.now())

    def has_delete_permission(self, request, obj=None):
        return False


# Business ADMIN manages role/active through the restricted account pages.
# Only Django superusers may use the generic User/Group editors.
from django.contrib.auth.models import User, Group
from django.contrib.auth.admin import UserAdmin, GroupAdmin


class SuperuserOnlyAdminMixin:
    def has_module_permission(self, request):
        return request.user.is_active and request.user.is_superuser

    def has_view_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_add_permission(self, request):
        return self.has_module_permission(request)

    def has_change_permission(self, request, obj=None):
        return self.has_module_permission(request)

    def has_delete_permission(self, request, obj=None):
        return self.has_module_permission(request)


admin.site.unregister(User)
admin.site.unregister(Group)
admin.site.register(User, type('ProtectedUserAdmin', (SuperuserOnlyAdminMixin, UserAdmin), {}))
admin.site.register(Group, type('ProtectedGroupAdmin', (SuperuserOnlyAdminMixin, GroupAdmin), {}))


from .models import Area, RestaurantTable


class ReadOnlyResourceAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Area)
class AreaAdmin(ReadOnlyResourceAdmin):
    list_display = ('name', 'is_active')


@admin.register(RestaurantTable)
class RestaurantTableAdmin(ReadOnlyResourceAdmin):
    list_display = ('code', 'area', 'capacity', 'status', 'is_active')


from .models import BookingItem
admin.site.register(BookingItem,ReadOnlyResourceAdmin)


from .models import Supplier,Ingredient,RecipeIngredient,Order,OrderItem,Invoice,Payment,StockReceipt,StockReceiptItem,StockIssue,StockIssueItem,StockMovement
# The management screens call transactional services. Generic editors must not
# bypass price snapshots, state machines or stock/payment accounting.
for business_model in (Supplier,Ingredient,RecipeIngredient,Order,OrderItem,Invoice,Payment,StockReceipt,StockReceiptItem,StockIssue,StockIssueItem,StockMovement):
    admin.site.register(business_model,ReadOnlyResourceAdmin)
