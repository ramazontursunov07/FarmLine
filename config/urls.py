from django.conf import settings
from django.conf.urls.static import static
from django.contrib import admin
from django.http import FileResponse, HttpResponseNotFound
from django.urls import path, include, re_path
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from drf_yasg.views import get_schema_view
from rest_framework import permissions


class JWTSchemaGenerator(OpenAPISchemaGenerator):
    def get_security_definitions(self):
        security_definitions = super().get_security_definitions()
        security_definitions['Bearer'] = {
            'type': 'apiKey',
            'name': 'Authorization',
            'in': 'header'
        }
        return security_definitions


schema_view = get_schema_view(
    openapi.Info(
        title="FarmLine API",
        default_version='v1',
        description="Fermerlar va chorvachilik/parrandachilik xo'jaliklari uchun boshqaruv platformasi API'si",
    ),
    public=True,
    permission_classes=[permissions.AllowAny],
    generator_class=JWTSchemaGenerator
)


def spa_index(request, *args, **kwargs):
    """React ilovasining kirish sahifasi: /dashboard kabi manzillarni brauzerdagi React o'zi boshqaradi."""
    index = settings.BASE_DIR / 'frontend' / 'dist' / 'index.html'
    if not index.is_file():
        return HttpResponseNotFound('Frontend yig\'ilmagan: frontend papkasida "npm run build" ni ishga tushiring.')
    response = FileResponse(open(index, 'rb'), content_type='text/html; charset=utf-8')
    response['Cache-Control'] = 'no-cache'  # yangi versiya chiqqanda eski sahifa ko'rinib qolmasin
    return response


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('apps.users.urls')),
    path('api/', include('apps.farms.urls')),
    path('api/', include('apps.finance.urls')),
    path('api/', include('apps.animals.urls')),
    path('api/', include('apps.tasks.urls')),
    path('api/', include('apps.inventory.urls')),
    path('api/', include('apps.assistant.urls')),
]

# Swagger/Redoc faqat ishlab chiqish (DEBUG) rejimida ochiq bo'ladi
if settings.DEBUG:
    urlpatterns += [
        re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
        path('', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
        path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc'),
    ]
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

# Boshqa hamma manzil React ilovasiga (API, admin va static bundan mustasno). Eng oxirida turishi kerak.
urlpatterns += [
    re_path(r'^(?!api/|admin/|static/|media/|swagger|redoc).*$', spa_index),
]
