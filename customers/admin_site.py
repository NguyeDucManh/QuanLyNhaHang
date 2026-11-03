from django.contrib.admin.apps import AdminConfig
from django.contrib.admin import AdminSite


class RestaurantAdminSite(AdminSite):
    def has_permission(self, request):
        from .rbac import is_admin
        return request.user.is_staff and is_admin(request.user)


class RestaurantAdminConfig(AdminConfig):
    default_site = 'customers.admin_site.RestaurantAdminSite'
