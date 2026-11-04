from django.urls import path

from . import views

app_name = 'administracion'

urlpatterns = [
    path('mesas/', views.lista_mesas, name='lista_mesas'),
    path('mesas/nueva/', views.crear_mesa, name='crear_mesa'),
    path('mesas/<int:id>/', views.detalle_mesa, name='detalle_mesa'),
    path('mesas/<int:id>/editar/', views.editar_mesa, name='editar_mesa'),
    path('mesas/<int:id>/deshabilitar/', views.deshabilitar_mesa, name='deshabilitar_mesa'),
    path('mesas/<int:id>/habilitar/', views.habilitar_mesa, name='habilitar_mesa'),

    path('clientes/', views.lista_clientes, name='lista_clientes'),
    path('clientes/nuevo/', views.crear_cliente, name='crear_cliente'),
    path('clientes/<int:id>/', views.detalle_cliente, name='detalle_cliente'),
    path('clientes/<int:id>/editar/', views.editar_cliente, name='editar_cliente'),
]
