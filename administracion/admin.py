from django.contrib import admin

from .models import Mesa, CategoriaProducto, Producto, Cliente


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'capacidad', 'ubicacion', 'estado', 'activo')
    list_filter = ('estado', 'activo')


@admin.register(CategoriaProducto)
class CategoriaProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo')


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'precio', 'disponible', 'activo')
    list_filter = ('categoria', 'disponible', 'activo')
    search_fields = ('nombre',)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'activo')
    search_fields = ('nombre', 'telefono')
