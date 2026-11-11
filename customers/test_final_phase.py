import json,math
from datetime import timedelta
from unittest.mock import patch
from types import SimpleNamespace
from django.test import SimpleTestCase,TestCase,Client
from django.core.exceptions import ValidationError,PermissionDenied
from django.utils import timezone
from django.contrib.auth.models import AnonymousUser
from django.urls import reverse
from .test_module07 import Module07Fixtures
from .models import RestaurantInfo,AttendanceLocationPolicy,AttendanceLocationEvent,Attendance,AIMessage,MenuItem,FaceChallenge,FaceAudit
from .location_service import haversine,evaluate_location,secure_punch
from .ai.chatbot.normalization import price_entities,normalize
from .ai.chatbot.assistant_service import respond
from .ai.chatbot.intent_router import route
from .ai.chatbot.memory_service import booking_entities

class ParserAndGeographyTests(SimpleTestCase):
    def test_vietnamese_teencode_token_boundary(self):
        self.assertEqual(normalize('combo 2 ng nhiu'),'combo 2 nguoi bao nhieu'); self.assertIn('700k',normalize('có hs dưới 700k k')); self.assertEqual(normalize('nha hang co gi'),normalize('nhà hàng có gì'))
    def test_money_units_and_range(self):
        self.assertEqual(price_entities('món dưới 700k'),{'max_price':700000}); self.assertEqual(price_entities('hs dưới 1tr2'),{'max_price':1200000}); self.assertEqual(price_entities('từ 300 đến 700k'),{'min_price':300000,'max_price':700000}); self.assertEqual(price_entities('dưới 1,5tr'),{'max_price':1500000})
        self.assertEqual(price_entities('có món dưới 700 k k'),{'max_price':700000})
    def test_date_formats_and_no_ambiguous_time_guess(self):
        for value in ['18/10','18-10','ngày 18 tháng 10','18/10/2026']:
            self.assertEqual(booking_entities(value,{}).get('date'),'2026-10-18')
        self.assertEqual(booking_entities('7 giờ tối',{})['time'],'19:00:00'); self.assertTrue(booking_entities('7h',{})['ambiguous_time'])
        with self.assertRaises(ValidationError): booking_entities('31/02/2026',{})
    def test_realistic_routing(self):
        for query,intent in [('nhà hàng có gì','MENU_SEARCH'),('mua dưới 700k','MENU_SEARCH'),('combo 2 ng nhiu','COMBO_INFO'),('đơn tui đâu','MY_ORDER_STATUS'),('t trả tiền chưa','MY_PAYMENT_STATUS'),('giỏ có gì','CART_VIEW')]: self.assertEqual(route(query),intent)
    def test_haversine_known_distance_symmetry_dateline(self):
        self.assertAlmostEqual(haversine(0,0,0,1),111195.08,places=1); self.assertEqual(haversine(10,100,10,100),0); self.assertAlmostEqual(haversine(10,100,11,101),haversine(11,101,10,100)); self.assertLess(haversine(0,179.999,0,-179.999),225)
    def test_invalid_coordinates_nan_boolean(self):
        for value in [float('nan'),float('inf'),True,None,'abc',91]:
            with self.assertRaises(ValidationError): haversine(value,0,0,0)
    def test_geofence_inside_outside_accuracy_and_boundary(self):
        info=SimpleNamespace(latitude=0,longitude=0); policy=SimpleNamespace(attendance_radius_m=150,max_accuracy_m=50)
        for point,status in [({'latitude':0,'longitude':0,'accuracy':10},'ALLOWED'),({'latitude':0,'longitude':.01,'accuracy':10},'DENIED'),({'latitude':0,'longitude':0,'accuracy':51},'ACCURACY_LOW')]: self.assertEqual(evaluate_location(point,info,policy)['geo_status'],status)
        lng=math.degrees(150/6371008.8); self.assertLessEqual(haversine(0,0,0,lng),150.000001)
        self.assertEqual(evaluate_location({'latitude':0,'longitude':0,'accuracy':50},info,policy)['geo_status'],'ALLOWED')

class FinalIntegrationTests(Module07Fixtures,TestCase):
    @classmethod
    def setUpTestData(cls): cls.initialize()
    def setUp(self):
        self.personnel(); self.info=RestaurantInfo.objects.create(name='Restaurant Test',opening_time='08:00',closing_time='23:00',latitude=10,longitude=106,is_active=True); self.policy=AttendanceLocationPolicy.objects.create(restaurant=self.info,mode='GPS_ONLY'); self.point={'latitude':10,'longitude':106,'accuracy':10}
    def request(self): return SimpleNamespace(user=AnonymousUser(),session={})
    def test_full_booking_slots_no_reask_known(self):
        memory={}; request=self.request(); answers=[respond(q,memory,request) for q in ['t muốn đặt bàn','6','18/10','7h tối']]
        self.assertEqual(memory['booking']['guests'],6); self.assertEqual(memory['booking']['date'],'2026-10-18'); self.assertEqual(memory['booking']['time'],'19:00:00'); self.assertNotIn('bao nhiêu người',answers[1]['answer']); self.assertNotIn('ngày nào',answers[2]['answer']); self.assertEqual(answers[-1]['tool'],'check_booking_availability')
    def test_ordinal_reference_then_add_selected_quantity(self):
        memory={}; request=self.request(); response=respond('món dưới 700k',memory,request); selected=memory['last_menu_ids'][1]; price=respond('món thứ 2 bao nhiêu',memory,request); self.assertEqual(memory['menu_item_id'],selected); result=respond('thêm 2 phần',memory,request); self.assertEqual(request.session['cart'][str(selected)],2)
    def test_live_db_price_range(self):
        from .ai.chatbot.tool_registry import menu_search
        self.menu.price=400000; self.menu.save(); self.second.price=800000; self.second.save(); rows=menu_search('món từ 300 đến 700k',limit=45); self.assertIn(self.menu.pk,[m.pk for m in rows]); self.assertNotIn(self.second.pk,[m.pk for m in rows]); self.assertTrue(all(300000<=m.price<=700000 for m in rows))
    def test_generic_menu_is_grounded_not_fallback(self):
        result=respond('nha hang co gi',{},self.request()); self.assertEqual(result['intent'],'MENU_SEARCH'); self.assertIn('Nhà hàng hiện có',result['answer']); self.assertNotIn('chưa có đủ thông tin',result['answer'])
    def test_secure_gps_success_and_no_duplicate(self):
        schedule=self.approved_schedule()
        with patch('customers.personnel_service.timezone.now',return_value=schedule.start_at+timedelta(minutes=1)):
            attendance,geo=secure_punch(actor=self.staff,schedule_id=schedule.pk,action='in',point=self.point); self.assertEqual(geo['geo_status'],'ALLOWED'); self.assertEqual(AttendanceLocationEvent.objects.get().attendance,attendance)
            with self.assertRaises(ValidationError): secure_punch(actor=self.staff,schedule_id=schedule.pk,action='in',point=self.point)
        self.assertEqual(AttendanceLocationEvent.objects.count(),1)
    def test_outside_or_low_accuracy_no_attendance_mutation(self):
        schedule=self.approved_schedule()
        for point in [{**self.point,'longitude':107},{**self.point,'accuracy':90}]:
            with self.assertRaises(ValidationError): secure_punch(actor=self.staff,schedule_id=schedule.pk,action='in',point=point)
        self.assertEqual(Attendance.objects.count(),0); self.assertEqual(AttendanceLocationEvent.objects.count(),2)
    def test_client_fake_distance_and_verified_cannot_bypass(self):
        client=Client(); client.force_login(self.staff); schedule=self.approved_schedule(); data={'schedule':schedule.pk,'action':'in','location':{**self.point,'longitude':107,'distance':0,'inside':True},'verified':True,'employee_id':self.employee.pk}; response=client.post(reverse('secure_attendance'),json.dumps(data),content_type='application/json'); self.assertEqual(response.status_code,400); self.assertEqual(Attendance.objects.count(),0)
    def test_legacy_punch_and_old_face_endpoint_do_not_bypass_policy(self):
        self.policy.mode='FACE_AND_GPS'; self.policy.save(); client=Client(); client.force_login(self.staff); schedule=self.approved_schedule(); self.assertEqual(client.post(reverse('attendance_punch',args=[schedule.pk]),{'action':'in'}).status_code,302); response=client.post(reverse('face_verify'),json.dumps({'schedule':schedule.pk,'action':'in','verified':True}),content_type='application/json'); self.assertEqual(response.status_code,400); self.assertEqual(Attendance.objects.count(),0)
    def test_policy_missing_or_disabled_fails_closed(self):
        self.policy.is_active=False; self.policy.save()
        with self.assertRaises(ValidationError): secure_punch(actor=self.staff,schedule_id=1,action='in',point=self.point)
    def test_face_failure_is_audited_and_never_writes_attendance(self):
        self.policy.mode='FACE_AND_GPS'; self.policy.save(); schedule=self.approved_schedule()
        with patch('customers.ai.face.face_enrollment_service.verify_identity',side_effect=ValidationError('liveness failed')):
            with self.assertRaises(ValidationError): secure_punch(actor=self.staff,schedule_id=schedule.pk,action='in',point=self.point,frames=[])
        self.assertEqual(Attendance.objects.count(),0); self.assertEqual(FaceAudit.objects.count(),1)
    def test_preview_does_not_track_location(self):
        client=Client(); client.force_login(self.staff); response=client.post(reverse('location_check'),json.dumps({'location':self.point}),content_type='application/json'); self.assertEqual(response.status_code,200); self.assertEqual(AttendanceLocationEvent.objects.count(),0)
    def test_geo_settings_and_face_pages_rbac(self):
        client=Client(); client.force_login(self.customer)
        for name in ['location_settings','face_test_page','ai_chatbot_management']: self.assertEqual(client.get(reverse(name)).status_code,403)
        client.force_login(self.manager)
        self.assertEqual(client.get(reverse('location_settings')).status_code,403)
        for name in ['face_test_page','ai_chatbot_management','ai_faces']: self.assertEqual(client.get(reverse(name)).status_code,200)
    def test_csrf_and_http_method_security(self):
        client=Client(enforce_csrf_checks=True); client.force_login(self.staff); self.assertEqual(client.post(reverse('secure_attendance'),'{}',content_type='application/json').status_code,403); self.assertEqual(client.get(reverse('secure_attendance')).status_code,405)
    def test_invalid_topping_does_not_mutate_cart(self):
        client=Client(); response=client.post(reverse('update_cart',args=[self.menu.pk]),{'topping_selection':'1','toppings':['999999']},HTTP_ACCEPT='application/json'); self.assertEqual(response.status_code,400); self.assertFalse(client.session.get('cart'))
    def test_detail_quantity_add(self):
        client=Client(); response=client.post(reverse('update_cart',args=[self.menu.pk]),{'quantity':'3'},HTTP_ACCEPT='application/json'); self.assertEqual(response.status_code,200); self.assertEqual(client.session['cart'][str(self.menu.pk)],3)
    def test_ai_history_ownership_session_and_no_store(self):
        one=Client();two=Client();one.force_login(self.customer);two.force_login(self.manager)
        one.post(reverse('ai_chat_message'),json.dumps({'message':'nhà hàng có gì'}),content_type='application/json')
        owned=one.get(reverse('ai_chat_history'));self.assertEqual(len(owned.json()['messages']),1);self.assertEqual(owned['Cache-Control'],'no-store');self.assertEqual(two.get(reverse('ai_chat_history')).json()['messages'],[])
