"""Internal reference recipes, never used for selling or inventory deduction."""
from django.db import models


class RecipeReference(models.Model):
    code = models.CharField("Mã công thức", max_length=32, unique=True)
    name = models.CharField("Tên món tham khảo", max_length=160, unique=True)
    category = models.CharField("Nhóm món", max_length=40)
    estimated_minutes = models.PositiveSmallIntegerField("Thời gian tham khảo (phút)")
    ingredients = models.JSONField("Định lượng tham khảo", default=list)
    steps = models.JSONField("Các bước tham khảo", default=list)
    source = models.CharField(max_length=20, default="DEMO_REFERENCE", editable=False)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["code"]
        verbose_name = "Công thức tham khảo"
        verbose_name_plural = "Công thức tham khảo"
        default_permissions = ("view",)

    def __str__(self):
        return f"{self.code} · {self.name}"
