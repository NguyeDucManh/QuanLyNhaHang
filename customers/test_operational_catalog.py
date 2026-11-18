from unittest.mock import patch
from django.test import TestCase
from django.core.exceptions import ValidationError
from .test_staff_roster import RosterData
from .operational_catalog import apply_catalog,preview_catalog,menu_snapshot
from .models import Ingredient,StockMovement

class ReferenceCatalogTests(RosterData,TestCase):
    @classmethod
    def setUpTestData(cls):cls.setup_data()
    def entries(self):return [{'model':'Ingredient','verified':True,'source':'Bảng danh mục quản trị đã xác nhận','values':{'code':'VIT','name':'Thịt vịt','unit':'kg','minimum_stock':'2'}}]
    def test_create_only_idempotent_no_stock_or_menu_changes(self):
        before=menu_snapshot();entries=self.entries();preview=preview_catalog(entries)
        self.assertEqual(Ingredient.objects.count(),0)
        self.assertEqual(len(apply_catalog(entries,actor=self.admin,approved_digest=preview['digest'])),1)
        self.assertEqual(apply_catalog(entries,actor=self.admin,approved_digest=preview['digest']),[])
        self.assertEqual(menu_snapshot(),before);self.assertEqual(Ingredient.objects.get().current_stock,0)
        self.assertFalse(StockMovement.objects.exists())
    def test_menu_unverified_contacts_and_stock_payload_are_rejected(self):
        for entries in ([{'model':'MenuItem','verified':True,'source':'not allowed','values':{}}],[{'model':'Supplier','verified':False,'values':{'code':'NCC','name':'Chưa xác nhận'}}],[{**self.entries()[0],'values':{**self.entries()[0]['values'],'current_stock':100}}]):
            with self.subTest(entries=entries),self.assertRaises(ValidationError):preview_catalog(entries)
    def test_name_duplicate_and_existing_updates_are_not_silently_skipped(self):
        entries=self.entries();apply_catalog(entries,actor=self.admin,approved_digest=preview_catalog(entries)['digest'])
        for changes in ({'code':'VIT2'},{'minimum_stock':'999'}):
            altered=[{**entries[0],'values':{**entries[0]['values'],**changes}}]
            with self.assertRaises(ValidationError):preview_catalog(altered)
    def test_audit_failure_rolls_back_reference_addition(self):
        entries=self.entries();token=preview_catalog(entries)['digest']
        with patch('customers.operational_catalog.record',side_effect=RuntimeError('test rollback')):
            with self.assertRaises(RuntimeError):apply_catalog(entries,actor=self.admin,approved_digest=token)
        self.assertFalse(Ingredient.objects.exists())
