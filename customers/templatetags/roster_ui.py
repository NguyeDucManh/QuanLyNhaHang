from django import template
from django.utils.html import strip_spaces_between_tags
from django.utils.safestring import mark_safe
register=template.Library()

@register.filter(is_safe=True)
def roster_form(form):
    # Django forms escape their labels/values/errors. Remove formatting-only
    # whitespace so the legacy operational phone-placeholder middleware does
    # not turn widget indentation into "Chưa cập nhật". Scope to roster forms;
    # do not change global presentation or any menu rendering behavior.
    return mark_safe(strip_spaces_between_tags(str(form.as_p())))
