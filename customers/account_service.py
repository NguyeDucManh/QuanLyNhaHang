"""Account changes are role-gated and protect superusers and the last administrator."""
from django.contrib.auth.models import User
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from .rbac import is_admin, assign_role


@transaction.atomic
def update_account(actor, target_id, role, is_active):
    # Serialize active-account changes so concurrent demotions cannot remove all admins.
    list(User.objects.select_for_update().filter(is_active=True).order_by('pk'))
    actor = User.objects.get(pk=actor.pk)
    if not is_admin(actor):
        raise PermissionDenied('Chỉ ADMIN được quản lý tài khoản.')
    target = User.objects.select_for_update().get(pk=target_id)
    if target.is_superuser and not actor.is_superuser:
        raise PermissionDenied('Chỉ superuser được quản lý superuser.')
    if target.pk == actor.pk and (not is_active or role != 'ADMIN'):
        raise ValidationError('Không được tự khóa hoặc hạ vai trò quản trị của chính mình.')
    if target.is_superuser and role != 'ADMIN':
        raise ValidationError('Superuser luôn có vai trò ADMIN.')
    if is_admin(target) and (not is_active or role != 'ADMIN'):
        others = User.objects.filter(is_active=True).exclude(pk=target.pk)
        if not others.filter(is_superuser=True).exists() and not others.filter(groups__name='ADMIN').exists():
            raise ValidationError('Phải giữ ít nhất một quản trị viên đang hoạt động.')
    assign_role(target, role)
    target.is_active = is_active
    target.save(update_fields=['is_active'])
    return target
