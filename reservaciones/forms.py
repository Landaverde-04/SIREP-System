from datetime import datetime, timedelta
from decimal import Decimal

from django import forms
from django.core.exceptions import ValidationError
from django.utils import timezone

from administracion.models import Cliente, Mesa, normalizar_nombre, normalizar_telefono
from .models import Reservacion
from .servicios import ServicioDisponibilidad


ACCION_CONSULTAR = 'consultar'
ACCION_CONFIRMAR = 'confirmar'


class FormularioBase(forms.Form):
    """Agrega las clases de Bootstrap a todos los campos."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            widget = campo.widget
            if isinstance(widget, (forms.RadioSelect, forms.HiddenInput)):
                continue
            clase = 'form-select' if isinstance(widget, forms.Select) else 'form-control'
            widget.attrs.setdefault('class', clase)

    def add_error(self, field, error):
        super().add_error(field, error)
        # Resalta en rojo los campos con error (clase de Bootstrap).
        for nombre in self.errors:
            if nombre in self.fields:
                attrs = self.fields[nombre].widget.attrs
                if 'is-invalid' not in attrs.get('class', ''):
                    attrs['class'] = (attrs.get('class', '') + ' is-invalid').strip()

    @property
    def accion(self):
        return self.data.get('accion', ACCION_CONSULTAR) if self.is_bound else ACCION_CONSULTAR

    @property
    def confirmando(self):
        return self.accion == ACCION_CONFIRMAR


class PeriodoForm(FormularioBase):
    """Fecha, hora, duración y cantidad de personas (CU-02 paso 3)."""

    fecha = forms.DateField(label='Fecha', widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    hora = forms.TimeField(label='Hora de inicio', widget=forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'))
    duracion_horas = forms.DecimalField(
        label='Duración estimada (horas)', initial=Decimal('2'), max_digits=3, decimal_places=1,
        widget=forms.NumberInput(attrs={'step': '0.5', 'min': '0.5'}),
        help_text='Dos horas por defecto; máximo cuatro.',
    )
    cantidad_personas = forms.IntegerField(
        label='Cantidad de personas', min_value=1, max_value=50,
        widget=forms.NumberInput(attrs={'min': '1'}),
    )

    def __init__(self, *args, disponibilidad=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.disponibilidad = disponibilidad or ServicioDisponibilidad()
        if not self.is_bound and 'fecha' not in self.initial:
            self.initial['fecha'] = timezone.localdate()

    def clean(self):
        datos = super().clean()
        fecha, hora, horas = datos.get('fecha'), datos.get('hora'), datos.get('duracion_horas')
        if fecha is None or hora is None or horas is None:
            return datos

        inicio = timezone.make_aware(datetime.combine(fecha, hora))
        duracion = timedelta(minutes=int(horas * 60))
        try:
            self.disponibilidad.validar_periodo(inicio, duracion)
        except ValidationError as error:
            campo = 'duracion_horas' if error.code and error.code.startswith('duracion') else 'hora'
            self.add_error(campo, error)
            return datos

        datos['inicio'] = inicio
        datos['duracion'] = duracion
        return datos

    @classmethod
    def iniciales_desde(cls, reservacion):
        inicio = timezone.localtime(reservacion.fecha_hora_inicio)
        return {
            'fecha': inicio.date(),
            'hora': inicio.time().replace(second=0, microsecond=0),
            'duracion_horas': Decimal(reservacion.duracion_estimada.total_seconds() / 3600).quantize(Decimal('0.1')),
            'cantidad_personas': reservacion.cantidad_personas,
        }


class DisponibilidadForm(PeriodoForm):
    """CU-02: la cantidad de personas es opcional; sin ella se muestran todas las mesas."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        campo = self.fields['cantidad_personas']
        campo.required = False
        campo.label = 'Personas (opcional)'
        campo.widget.attrs['placeholder'] = 'Todas'


class ReservacionForm(PeriodoForm):
    """
    CU-01 / CU-05. Se envía en dos pasos: "consultar" muestra las mesas
    disponibles (CU-02) y "confirmar" guarda la reservación.
    """

    mesa = forms.ModelChoiceField(
        label='Mesa', queryset=Mesa.objects.filter(activo=True), required=False,
        widget=forms.RadioSelect, empty_label=None,
        error_messages={'invalid_choice': 'Seleccione una de las mesas disponibles.'},
    )
    cliente = forms.ModelChoiceField(
        label='Cliente', queryset=Cliente.objects.filter(activo=True), required=False,
        widget=forms.HiddenInput,
        error_messages={'invalid_choice': 'El cliente seleccionado no existe.'},
    )

    def __init__(self, *args, pedir_cliente=True, **kwargs):
        super().__init__(*args, **kwargs)
        self.pedir_cliente = pedir_cliente
        if not pedir_cliente:
            del self.fields['cliente']

    def clean(self):
        datos = super().clean()
        if self.confirmando:
            if not datos.get('mesa') and 'mesa' not in self.errors:
                self.add_error('mesa', 'Seleccione una de las mesas disponibles.')
            if self.pedir_cliente and not datos.get('cliente') and 'cliente' not in self.errors:
                self.add_error('cliente', 'Busque y seleccione al cliente, o regístrelo si es nuevo.')
        return datos


class ClienteRapidoForm(forms.ModelForm):
    """CU-04: alta rápida con nombre y teléfono."""

    telefono = forms.CharField(label='Teléfono', max_length=20)

    class Meta:
        model = Cliente
        fields = ['nombre', 'telefono']
        widgets = {
            'nombre': forms.TextInput(attrs={'class': 'form-control', 'autocomplete': 'off'}),
            'telefono': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '7777-8888',
                                               'inputmode': 'tel', 'autocomplete': 'off'}),
        }

    def clean_telefono(self):
        return normalizar_telefono(self.cleaned_data['telefono'])

    def clean_nombre(self):
        nombre = normalizar_nombre(self.cleaned_data['nombre'])
        if not nombre:
            raise ValidationError('Ingrese el nombre del cliente.')
        return nombre

    def validate_unique(self):
        # El teléfono repetido no se trata como error del formulario: la vista
        # ofrece seleccionar al cliente existente (CU-04 6a).
        pass


class CancelarReservacionForm(FormularioBase):
    motivo = forms.CharField(
        label='Motivo de la cancelación (opcional)', required=False, max_length=255,
        widget=forms.Textarea(attrs={'rows': 2}),
    )


class BuscarReservacionForm(FormularioBase):
    """CU-07 y filtros del listado."""

    TODAS = ''
    q = forms.CharField(label='Buscar', required=False,
                        widget=forms.TextInput(attrs={'placeholder': 'Código, nombre o teléfono del cliente'}))
    fecha = forms.DateField(label='Fecha', required=False,
                            widget=forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'))
    estado = forms.ChoiceField(label='Estado', required=False,
                               choices=[(TODAS, 'Todos')] + list(Reservacion.Estado.choices))


class IngresoForm(FormularioBase):
    """CU-03: personas que llegaron y, si hace falta, otra mesa."""

    cantidad_personas = forms.IntegerField(label='Personas que llegaron', min_value=1, max_value=50,
                                           widget=forms.NumberInput(attrs={'min': '1'}))
    mesa = forms.ModelChoiceField(
        label='Mesa', queryset=Mesa.objects.filter(activo=True), required=False,
        widget=forms.RadioSelect, empty_label=None,
        error_messages={'invalid_choice': 'Seleccione una de las mesas disponibles.'},
    )
    cliente = forms.ModelChoiceField(
        label='Cliente', queryset=Cliente.objects.filter(activo=True), required=False,
        widget=forms.HiddenInput,
    )

    def exigir_mesa(self):
        if not self.cleaned_data.get('mesa') and 'mesa' not in self.errors:
            self.add_error('mesa', 'Seleccione una de las mesas disponibles.')
            return False
        return True
