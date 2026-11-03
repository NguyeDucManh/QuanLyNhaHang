from django.core.management.base import BaseCommand, CommandError
from django.contrib.auth.models import Group, Permission, User
from django.db import transaction
from customers.rbac import ROLES, assign_role, MANAGER_PERMISSIONS, STAFF_ORDER_PERMISSIONS, STAFF_PAYMENT_PERMISSIONS


class Command(BaseCommand):
    help = 'Seed four business roles and existing-module permissions; idempotent.'

    @transaction.atomic
    def handle(self, *args, **options):
        groups = {role: Group.objects.get_or_create(name=role)[0] for role in ROLES}
        # Only existing models. No wildcard grants for future modules.
        groups['ADMIN'].permissions.add(*Permission.objects.filter(content_type__app_label='customers'))
        groups['ADMIN'].permissions.add(*Permission.objects.filter(content_type__app_label='auth', codename__in=['view_user', 'change_user']))
        groups['MANAGER'].permissions.add(*Permission.objects.filter(content_type__app_label='customers', codename__in=MANAGER_PERMISSIONS))
        groups['STAFF'].permissions.add(*Permission.objects.filter(content_type__app_label='customers', codename__in=STAFF_ORDER_PERMISSIONS | STAFF_PAYMENT_PERMISSIONS))
        assigned = 0
        for user in User.objects.all():
            roles = list(user.groups.filter(name__in=ROLES).values_list('name', flat=True))
            if len(roles) > 1 and not user.is_superuser:
                raise CommandError(f'Tài khoản {user.pk} có nhiều role nghiệp vụ. Cần sửa trước khi seed.')
            if not roles:
                # Safe one-time legacy classification; never promote an is_staff user to ADMIN.
                assign_role(user, 'ADMIN' if user.is_superuser else 'STAFF' if user.is_staff else 'CUSTOMER')
                assigned += 1
        self.stdout.write(self.style.SUCCESS(f'Roles: {", ".join(ROLES)}. Assigned existing accounts: {assigned}.'))
