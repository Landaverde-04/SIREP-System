from django.contrib import admin

from .models import Cliente, Mesa


@admin.register(Mesa)
class MesaAdmin(admin.ModelAdmin):
    list_display = ('numero', 'capacidad', 'ubicacion', 'activo')
    list_filter = ('activo',)
    ordering = ('numero',)


@admin.register(Cliente)
class ClienteAdmin(admin.ModelAdmin):
    list_display = ('nombre', 'telefono', 'activo')
    search_fields = ('nombre', 'telefono')
