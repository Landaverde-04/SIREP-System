from django.urls import path

from . import views

app_name = 'reservaciones'

urlpatterns = [
    path('', views.lista_reservaciones, name='lista_reservaciones'),
    path('disponibilidad/', views.consultar_disponibilidad, name='consultar_disponibilidad'),
    path('nueva/', views.crear_reservacion, name='crear_reservacion'),

    # Ingreso de clientes (CU-03)
    path('ingresos/', views.panel_ingresos, name='panel_ingresos'),
    path('ingresos/sin-reservacion/', views.ingreso_sin_reservacion, name='ingreso_sin_reservacion'),
    path('ingresos/<str:codigo>/', views.ingreso_con_reservacion, name='ingreso_con_reservacion'),

    # Registro rápido de clientes (CU-04), usado desde los formularios
    path('clientes/buscar/', views.buscar_clientes, name='buscar_clientes'),
    path('clientes/nuevo/', views.registrar_cliente, name='registrar_cliente'),

    path('<str:codigo>/', views.detalle_reservacion, name='detalle_reservacion'),
    path('<str:codigo>/modificar/', views.modificar_reservacion, name='modificar_reservacion'),
    path('<str:codigo>/cancelar/', views.cancelar_reservacion, name='cancelar_reservacion'),
]
