from django.urls import path
from . import views

app_name = 'core'

urlpatterns = [
    path('', views.home, name='home'),
    path('healthz/', views.estado_servicio, name='estado_servicio'),
    path('modulos/<slug:modulo>/', views.modulo, name='modulo'),
]
