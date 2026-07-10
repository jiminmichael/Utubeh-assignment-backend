from django.conf import settings
from django.conf.urls.static import static
"""
URL configuration for asset_management project.

The `urlpatterns` list routes URLs to views. For more information please see:
    https://docs.djangoproject.com/en/4.2/topics/http/urls/
Examples:
Function views
    1. Add an import:  from my_app import views
    2. Add a URL to urlpatterns:  path('', views.home, name='home')
Class-based views
    1. Add an import:  from other_app.views import Home
    2. Add a URL to urlpatterns:  path('', Home.as_view(), name='home')
Including another URLconf
    1. Import the include() function: from django.urls import include, path
    2. Add a URL to urlpatterns:  path('blog/', include('blog.urls'))
"""
from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import SpectacularAPIView, SpectacularRedocView, SpectacularSwaggerView

urlpatterns = [
    path('admin/', admin.site.urls),

    # API routes
    path('api/accounts/', include('accounts.urls', namespace='accounts')),
    path('api/assets/', include('assets.urls', namespace='assets')),
    path('api/maintenance/', include('maintenance.urls', namespace='maintenance')),
    path('api/notifications/', include('notifications.urls', namespace='notifications')),
    path('api/reports/', include('reports.urls', namespace='reports')),

    # API Schema and Documentation
    path('api/schema/', SpectacularAPIView.as_view(), name='schema'),
    path('api/docs/', SpectacularSwaggerView.as_view(url_name='schema'), name='swagger-ui'),
    path('api/redoc/', SpectacularRedocView.as_view(url_name='schema'), name='redoc'),
]

if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)

handler401 = 'core.views.handler401'
handler403 = 'core.views.handler403'
handler404 = 'core.views.handler404'
handler500 = 'core.views.handler500'