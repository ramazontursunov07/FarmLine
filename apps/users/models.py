from django.db import models
from django.contrib.auth.models import AbstractUser


class User(AbstractUser):
    ROLE_CHOICES = (
        ('admin', 'Admin'),
        ('fermer', 'Fermer'),
        ('ishchi', 'Ishchi')
    )
    role = models.CharField(choices=ROLE_CHOICES, max_length=10, default='fermer')
    phone_number = models.CharField(max_length=20, blank=True, null=True)

    def __str__(self):
        return self.username
