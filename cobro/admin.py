from django.contrib import admin

from .models import Cobro, DetalleCobro


class DetalleCobroInline(admin.TabularInline):
    model = DetalleCobro
    extra = 0
    can_delete = False
    readonly_fields = ('detalle_pedido', 'nombre_producto', 'cantidad', 'precio_unitario', 'subtotal')

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.has_perm('cobro.view_cobro')


@admin.register(Cobro)
class CobroAdmin(admin.ModelAdmin):
    list_display = ('id', 'atencion', 'total', 'forma_pago', 'cajero', 'fecha_hora_pago')
    list_filter = ('forma_pago', 'fecha_hora_pago')
    search_fields = ('=id', '=atencion__id', 'cajero__username')
    readonly_fields = ('atencion', 'total', 'monto_recibido', 'forma_pago', 'cambio',
                       'fecha_hora_pago', 'cajero', 'fecha_creacion', 'fecha_modificacion', 'activo')
    inlines = [DetalleCobroInline]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
