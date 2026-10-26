"""Ferma ichidagi rollar: ferma egasi, ishchi, veterinar."""
from .models import Worker

# Veterinar yoza oladigan ferma ishlari turlari
VET_EVENT_TYPES = ('kasallik', 'davolash', 'vaksinatsiya')


def is_vet(user, farm):
    """Foydalanuvchi shu fermada veterinar (ferma egasi emas)mi?"""
    if farm.owner_id == user.id:
        return False
    return Worker.objects.filter(farm=farm, user=user, kind='veterinar').exists()
