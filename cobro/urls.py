from django.urls import path

from . import views


app_name = 'cobro'

urlpatterns = [
    path('', views.lista_atenciones, name='lista_atenciones'),
    path('atenciones/<int:id>/', views.detalle_consumo, name='detalle_consumo'),
    path('atenciones/<int:id>/registrar/', views.registrar_cobro, name='registrar_cobro'),
    path('historial/', views.historial, name='historial'),
    path('<int:id>/', views.detalle_cobro, name='detalle_cobro'),
]
