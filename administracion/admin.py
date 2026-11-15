from django.contrib import admin

from .models import CategoriaProducto, Cliente, Mesa, Producto


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'capacidad', 'ubicacion', 'activo')
    list_filter = ('activo',)
    ordering = ('numero',)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'activo')
    search_fields = ('nombre', 'telefono')


@admin.register(CategoriaProducto)
class CategoriaProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'activo')


@admin.register(Producto)
class ProductoAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'categoria', 'precio', 'disponible', 'activo')
    list_filter = ('categoria', 'disponible', 'activo')
    search_fields = ('nombre',)
