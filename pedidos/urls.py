from django.urls import path

from . import views

app_name = 'pedidos'

urlpatterns = [
    path('', views.lista_pedidos, name='lista_pedidos'),
    path('nuevo/', views.crear_pedido, name='crear_pedido'),
    path('cocina/', views.cocina, name='cocina'),
    path('<int:id>/', views.detalle_pedido, name='detalle_pedido'),
    path('<int:id>/editar/', views.editar_pedido, name='editar_pedido'),
    path('<int:id>/estado/<str:estado>/', views.cambiar_estado, name='cambiar_estado'),
]
