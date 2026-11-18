"""Isolated non-menu data expansion regression tests."""
from io import StringIO
from django.core.management import call_command, CommandError
from django.test import TestCase
from .models import MenuItem, RecipeIngredient, RecipeReference, Ingredient, Supplier, StockMovement, Payment, Booking, Order
from .management.commands.seed_reference_expansion import REFERENCES, SUPPLIERS, EXTRA_INGREDIENTS


class ReferenceExpansionTests(TestCase):
    def run_seed(self,apply=False):
        out=StringIO()
        call_command("seed_reference_expansion",**({"apply":True} if apply else {}),stdout=out)
        return out.getvalue()

    def test_catalog_has_fifty_distinct_quantified_references(self):
        self.assertEqual(len(REFERENCES),50)
        self.assertEqual(len({r["code"] for r in REFERENCES}),50)
        self.assertEqual(len({r["name"] for r in REFERENCES}),50)
        self.assertEqual(len(SUPPLIERS),5)
        self.assertEqual(len(EXTRA_INGREDIENTS),20)
        for recipe in REFERENCES:
            self.assertEqual(len(recipe["steps"]),5)
            self.assertTrue(recipe["ingredients"])
            self.assertTrue(all(float(i["quantity"])>0 and i["unit"] in ("kg","l","piece") for i in recipe["ingredients"]))

    def test_preview_does_not_write(self):
        self.run_seed()
        self.assertFalse(RecipeReference.objects.exists())
        self.assertFalse(Supplier.objects.exists())
        self.assertFalse(Ingredient.objects.exists())

    def test_apply_is_idempotent_and_preserves_business_data(self):
        before=dict(menus=list(MenuItem.objects.values()),recipes=list(RecipeIngredient.objects.values()),
                    bookings=Booking.objects.count(),orders=Order.objects.count(),payments=Payment.objects.count())
        self.run_seed(apply=True)
        self.assertEqual(RecipeReference.objects.count(),50)
        self.assertEqual(Supplier.objects.count(),5)
        self.assertEqual(Ingredient.objects.count(),20)
        self.assertFalse(Ingredient.objects.exclude(current_stock=0).exists())
        self.assertFalse(StockMovement.objects.exists())
        first=list(RecipeReference.objects.values())
        self.run_seed(apply=True)
        self.assertEqual(list(RecipeReference.objects.values()),first)
        self.assertEqual(RecipeReference.objects.count(),50)
        self.assertEqual(Supplier.objects.count(),5)
        self.assertEqual(Ingredient.objects.count(),20)
        self.assertEqual(list(MenuItem.objects.values()),before["menus"])
        self.assertEqual(list(RecipeIngredient.objects.values()),before["recipes"])
        self.assertEqual(Booking.objects.count(),before["bookings"])
        self.assertEqual(Order.objects.count(),before["orders"])
        self.assertEqual(Payment.objects.count(),before["payments"])

    def test_reject_existing_code_conflict_atomically(self):
        Supplier.objects.create(code="DEMO-NCC005",name="Tên đã có",is_active=False)
        with self.assertRaises(CommandError):
            self.run_seed(apply=True)
        self.assertFalse(RecipeReference.objects.exists())
        self.assertEqual(Supplier.objects.count(),1)
        self.assertFalse(Ingredient.objects.exists())

    def test_rerun_keeps_user_changes(self):
        self.run_seed(apply=True)
        ref=RecipeReference.objects.get(code="DEMO-CT001")
        ref.steps=["Bếp trưởng đã sửa"]; ref.save(update_fields=["steps"])
        supplier=Supplier.objects.get(code="DEMO-NCC004")
        supplier.is_active=False; supplier.save(update_fields=["is_active"])
        self.run_seed(apply=True)
        ref.refresh_from_db(); supplier.refresh_from_db()
        self.assertEqual(ref.steps,["Bếp trưởng đã sửa"])
        self.assertFalse(supplier.is_active)
