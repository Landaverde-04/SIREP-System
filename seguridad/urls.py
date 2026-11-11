from django.urls import path
from django.contrib.auth import views as auth_views
from . import views

app_name = 'seguridad'

urlpatterns = [
    path('login/', auth_views.LoginView.as_view(template_name='seguridad/login.html'), name='login'),
    path('logout/', auth_views.LogoutView.as_view(), name='logout'),

    # Usuarios
    path('usuarios/', views.lista_usuarios, name='lista_usuarios'),
    path('usuarios/crear/', views.crear_usuario, name='crear_usuario'),
    path('usuarios/<int:id>/', views.detalle_usuario, name='detalle_usuario'),
    path('usuarios/<int:id>/editar/', views.editar_usuario, name='editar_usuario'),
    path('usuarios/<int:id>/desactivar/', views.desactivar_usuario, name='desactivar_usuario'),
    path('usuarios/<int:id>/activar/', views.activar_usuario, name='activar_usuario'),
    # Compatibilidad con enlaces anteriores: esta ruta también realiza baja lógica.
    path('usuarios/<int:id>/eliminar/', views.desactivar_usuario, name='eliminar_usuario'),
    path('usuarios/<int:id>/resetear-password/', views.resetear_password, name='resetear_password'),

    # Empleados: independientes de las cuentas de usuario.
    path('empleados/', views.lista_empleados, name='lista_empleados'),
    path('empleados/crear/', views.crear_empleado, name='crear_empleado'),
    path('empleados/<int:id>/', views.detalle_empleado, name='detalle_empleado'),
    path('empleados/<int:id>/editar/', views.editar_empleado, name='editar_empleado'),
    path('empleados/<int:id>/usuarios-disponibles/', views.usuarios_disponibles_empleado, name='usuarios_disponibles_empleado'),
    path('empleados/<int:id>/asociar-usuario/', views.asociar_usuario_empleado, name='asociar_usuario_empleado'),
    path('empleados/<int:id>/desactivar/', views.desactivar_empleado, name='desactivar_empleado'),
    path('empleados/<int:id>/activar/', views.activar_empleado, name='activar_empleado'),

    # Roles
    path('roles/', views.lista_roles, name='lista_roles'),
    path('roles/crear/', views.crear_rol, name='crear_rol'),
    path('roles/<int:id>/editar/', views.editar_rol, name='editar_rol'),
    path('roles/<int:id>/eliminar/', views.eliminar_rol, name='eliminar_rol'),
    path('roles/<int:id>/usuarios/', views.usuarios_rol, name='usuarios_rol'),

    # Perfil propio
    path('mi-perfil/', views.mi_perfil, name='mi_perfil'),
    path('mi-perfil/cambiar-password/', views.CambiarPasswordView.as_view(), name='cambiar_password'),
]
