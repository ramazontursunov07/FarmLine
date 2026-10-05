from django.contrib import admin
from django.urls import path, include, re_path
from drf_yasg.views import get_schema_view
from drf_yasg import openapi
from drf_yasg.generators import OpenAPISchemaGenerator
from rest_framework import permissions
from django.conf import settings
from django.conf.urls.static import static
from rest_framework_simplejwt.views import TokenObtainPairView, TokenRefreshView, TokenVerifyView


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
        title="API",  # bu shunchaki swaggerda chiqadigan nomi
        default_version='v1',  # bu esa versiyasi
        description='E-commerce API',  # bu shunchaki description
        terms_of_service="https://www.com/policies/terms/",  # bunga shunchaki xohlagan urlimizni qo'ysak ham bo'ladi.
        contact=openapi.Contact(email="ramazontursunov007@gmail.com"),  # bunga o'zimizni urlimizni qo'ysak ham bo'ladi.
        license=openapi.License(name="BSD License")  # Licence
    ),
    public=True,  # bu hammaga ochiq ko'rinadi.
    permission_classes=[permissions.AllowAny],
    generator_class=JWTSchemaGenerator
)

urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/users/', include('apps.users.urls')),
    path('api/', include('apps.farms.urls')),
    path('api/', include('apps.finance.urls')),

    path('api/v1/auth/token/', TokenObtainPairView.as_view(), name='token_obtain_pair'),
    # bu ikkita token yaratib beradi.
    path('api/v1/auth/token/refresh/', TokenRefreshView.as_view(), name='token_refresh'),
    # bu esa refresh qilib beradi.
    path('api/v1/auth/token/verify/', TokenVerifyView.as_view(), name='token_verify'),
    # bu esa tokenni eskirganini tekshiradi.

    re_path(r'^swagger(?P<format>\.json|\.yaml)$', schema_view.without_ui(cache_timeout=0), name='schema-json'),
    path('', schema_view.with_ui('swagger', cache_timeout=0), name='schema-swagger-ui'),
    path('redoc/', schema_view.with_ui('redoc', cache_timeout=0), name='schema-redoc')
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
