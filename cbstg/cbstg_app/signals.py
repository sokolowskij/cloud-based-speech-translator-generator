from django.db.models.signals import post_migrate
from django.dispatch import receiver
from .models import Role
from django.db.models.signals import post_save
from django.contrib.auth import get_user_model

User = get_user_model()

@receiver(post_migrate)
def create_default_roles(sender, **kwargs):
    roles = [
        {
            'role_name': 'Free'
        },
        {
            'role_name': 'Premium',
            'daily_tts_limit': 10,
            'daily_stt_limit': 10,
            'char_limit': 450,
            'audio_duration_limit': 45
        },
        {
            'role_name': 'Enterprise',
            'daily_tts_limit': 20,
            'daily_stt_limit': 20,
            'char_limit': 600,
            'audio_duration_limit': 60
        },
        {
            'role_name': 'Admin',
            'daily_tts_limit': 999999,
            'daily_stt_limit': 999999,
            'char_limit': 600,
            'audio_duration_limit': 60
        },
    ]

    for role_data in roles:
        Role.objects.update_or_create(role_name=role_data['role_name'], defaults=role_data)


@receiver(post_save, sender=User)
def assign_admin_role_to_superuser(sender, instance, created, **kwargs):
    if instance.is_superuser:
        try:
            admin_role = Role.objects.get(role_name='Admin')
            if instance.role != admin_role:
                instance.role = admin_role
                instance.save(update_fields=['role'])
        except Role.DoesNotExist:
            pass
