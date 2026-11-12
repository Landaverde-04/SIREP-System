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

    # Categorías del menú
    path('categorias/', views.lista_categorias, name='lista_categorias'),
    path('categorias/crear/', views.crear_categoria, name='crear_categoria'),
    path('categorias/<int:id>/editar/', views.editar_categoria, name='editar_categoria'),
    path('categorias/<int:id>/estado/', views.alternar_categoria, name='alternar_categoria'),

    # Productos del menú
    path('productos/', views.lista_productos, name='lista_productos'),
    path('productos/crear/', views.crear_producto, name='crear_producto'),
    path('productos/<int:id>/', views.detalle_producto, name='detalle_producto'),
    path('productos/<int:id>/editar/', views.editar_producto, name='editar_producto'),
    path('productos/<int:id>/disponibilidad/', views.cambiar_disponibilidad, name='cambiar_disponibilidad'),
    path('productos/<int:id>/deshabilitar/', views.deshabilitar_producto, name='deshabilitar_producto'),
    path('productos/<int:id>/habilitar/', views.habilitar_producto, name='habilitar_producto'),

]
