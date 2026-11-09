from django.contrib import admin

from .models import DetallePedido, Pedido


class DetallePedidoInline(admin.TabularInline):
    model = DetallePedido
    extra = 0
    readonly_fields = ('precio_unitario',)


@admin.register(Pedido)
class PedidoAdmin(admin.ModelAdmin):
    list_display = ('id', 'mesa', 'mesero', 'estado', 'fecha_creacion')
    list_filter = ('estado',)
    search_fields = ('id', 'mesero__username', 'mesa__numero')
    inlines = [DetallePedidoInline]
