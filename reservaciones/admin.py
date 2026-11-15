from django.contrib import admin

from .models import Atencion, Reservacion


@admin.register(Reservacion)
class ReservacionAdmin(admin.ModelAdmin):
    list_display = ('codigo', 'cliente', 'mesa', 'fecha_hora_inicio', 'duracion_estimada',
                    'cantidad_personas', 'estado')
    list_filter = ('estado',)
    search_fields = ('codigo', 'cliente__nombre', 'cliente__telefono')
    readonly_fields = ('codigo',)


@admin.register(Atencion)
class AtencionAdmin(admin.ModelAdmin):
    list_display = ('id', 'mesa', 'cliente', 'reservacion', 'fecha_hora_ingreso', 'estado')
    list_filter = ('estado',)
