from django.conf import settings
from django.db import models

class IngredientSupplyPolicy(models.Model):
    ingredient = models.OneToOneField('Ingredient', on_delete=models.CASCADE, related_name='ai_supply_policy')
    supplier = models.ForeignKey('Supplier', null=True, blank=True, on_delete=models.PROTECT)
    lead_time_days = models.PositiveSmallIntegerField(default=2)
    safety_days = models.PositiveSmallIntegerField(default=3)
    class Meta:
        constraints = [models.CheckConstraint(condition=models.Q(lead_time_days__gte=1, lead_time_days__lte=30, safety_days__in=[3,5,7]), name='ai_supply_policy_valid')]

class FaceProfile(models.Model):
    employee = models.OneToOneField('Employee', on_delete=models.CASCADE, related_name='face_profile')
    model_version = models.CharField(max_length=100)
    threshold = models.FloatField(null=True, blank=True)
    calibration = models.JSONField(default=dict)
    enrolled_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

class FaceEmbedding(models.Model):
    profile = models.ForeignKey(FaceProfile, on_delete=models.CASCADE, related_name='samples')
    vector = models.JSONField()
    quality = models.JSONField(default=dict)
    image_hash = models.CharField(max_length=64)
    created_at = models.DateTimeField(auto_now_add=True)
    class Meta:
        constraints = [models.UniqueConstraint(fields=['profile','image_hash'], name='face_sample_unique')]

class FaceAudit(models.Model):
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)
    employee = models.ForeignKey('Employee', null=True, on_delete=models.SET_NULL)
    success = models.BooleanField(default=False)
    similarity = models.FloatField(null=True)
    threshold = models.FloatField(null=True)
    threshold_type = models.CharField(max_length=16, blank=True, default='')
    liveness = models.BooleanField(default=False)
    action = models.CharField(max_length=8, blank=True)
    reason = models.CharField(max_length=250)
    created_at = models.DateTimeField(auto_now_add=True)

class FaceChallenge(models.Model):
    import uuid
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    actor = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE)
    action = models.CharField(max_length=16)
    expires_at = models.DateTimeField()
    used_at = models.DateTimeField(null=True)

class AIConversation(models.Model):
    user = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, on_delete=models.CASCADE)
    session_key = models.CharField(max_length=40)
    memory = models.JSONField(default=dict)
    created_at = models.DateTimeField(auto_now_add=True)

class AIMessage(models.Model):
    conversation = models.ForeignKey(AIConversation, on_delete=models.CASCADE, related_name='messages')
    question = models.CharField(max_length=2000)
    answer = models.TextField()
    intent = models.CharField(max_length=40)
    tool = models.CharField(max_length=50, blank=True)
    sources = models.JSONField(default=list)
    created_at = models.DateTimeField(auto_now_add=True)
