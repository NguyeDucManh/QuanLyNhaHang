# Recipe references are separate from the live MenuItem / RecipeIngredient workflow.
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [("customers", "0025_staff_roster_registration")]

    operations = [
        migrations.CreateModel(
            name="RecipeReference",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("code", models.CharField(max_length=32, unique=True, verbose_name="Mã công thức")),
                ("name", models.CharField(max_length=160, unique=True, verbose_name="Tên món tham khảo")),
                ("category", models.CharField(max_length=40, verbose_name="Nhóm món")),
                ("estimated_minutes", models.PositiveSmallIntegerField(verbose_name="Thời gian tham khảo (phút)")),
                ("ingredients", models.JSONField(default=list, verbose_name="Định lượng tham khảo")),
                ("steps", models.JSONField(default=list, verbose_name="Các bước tham khảo")),
                ("source", models.CharField(default="DEMO_REFERENCE", editable=False, max_length=20)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
            ],
            options={
                "ordering": ["code"],
                "verbose_name": "Công thức tham khảo",
                "verbose_name_plural": "Công thức tham khảo",
                "default_permissions": ("view",),
            },
        ),
    ]
