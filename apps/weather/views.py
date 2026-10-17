from django.db.models import Q
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView

from apps.farms.models import Farm
from apps.users.permissions import is_app_admin

from . import services


class WeatherView(APIView):
    """GET /api/weather/?farm=<id> - ferma joylashuvi bo'yicha 7 kunlik ob-havo va ogohlantirishlar."""
    permission_classes = [IsAuthenticated]

    def get(self, request):
        farm_id = request.query_params.get('farm', '')
        if not farm_id.isdigit():
            raise ValidationError({'farm': 'Ferma ID si kerak.'})
        qs = Farm.objects.all() if is_app_admin(request.user) else Farm.objects.filter(
            Q(owner=request.user) | Q(workers__user=request.user)
        ).distinct()
        farm = qs.filter(pk=int(farm_id)).first()
        if farm is None:
            raise NotFound('Ferma topilmadi.')

        base = {'farm': farm.id, 'farm_name': farm.name, 'location': farm.location}
        try:
            if farm.latitude is None or farm.longitude is None:
                point = services.geocode(farm.location)
                if point is None:
                    return Response({**base, 'status': 'no_location'})
                farm.latitude, farm.longitude = point
                farm.save(update_fields=['latitude', 'longitude'])
            forecast = services.fetch_forecast(farm.latitude, farm.longitude)
        except services.WeatherError:
            return Response({**base, 'status': 'unavailable'})

        return Response({
            **base, 'status': 'ok',
            **forecast,
            'alerts': services.build_alerts(forecast['days']),
        })
