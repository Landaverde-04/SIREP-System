from django import forms
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.forms import BaseInlineFormSet, inlineformset_factory

from administracion.models import Mesa, Producto

from .models import DetallePedido, Pedido


class PedidoForm(forms.ModelForm):
    class Meta:
        model = Pedido
        fields = ('mesa', 'notas')
        labels = {'mesa': 'Mesa', 'notas': 'Notas del pedido'}
        widgets = {
            'mesa': forms.Select(attrs={'class': 'form-select'}),
            'notas': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 2,
                'placeholder': 'Ej: cliente alérgico al maní',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # RN-05: solo se toman pedidos en mesas con una atención abierta. Al
        # editar se conserva la mesa actual aunque su atención ya no lo esté,
        # para que el formulario pueda mostrarse.
        filtro = Q(activo=True, atenciones__estado='ABIERTA')
        if self.instance.pk:
            filtro |= Q(pk=self.instance.mesa_id)
        self.fields['mesa'].queryset = Mesa.objects.filter(filtro).distinct()
        self.fields['mesa'].empty_label = 'Seleccione una mesa'
        self.fields['mesa'].label_from_instance = (
            lambda mesa: f'{mesa} ({mesa.capacidad} personas)'
        )


class DetallePedidoForm(forms.ModelForm):
    class Meta:
        model = DetallePedido
        fields = ('producto', 'cantidad', 'nota')
        widgets = {
            'producto': forms.Select(attrs={'class': 'form-select'}),
            'cantidad': forms.NumberInput(attrs={
                'class': 'form-control',
                'min': 1,
            }),
            'nota': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Ej: sin cebolla',
            }),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # RN-06: solo se piden productos habilitados y disponibles. Al editar se
        # conserva el producto ya pedido aunque se haya agotado después.
        filtro = Q(activo=True, disponible=True)
        if self.instance.pk:
            filtro |= Q(pk=self.instance.producto_id)
        self.fields['producto'].queryset = Producto.objects.filter(filtro)
        self.fields['producto'].empty_label = 'Seleccione un producto'
        self.fields['producto'].label_from_instance = (
            lambda producto: f'{producto.nombre} (${producto.precio})'
        )

    def save(self, commit=True):
        detalle = super().save(commit=False)
        # El precio se fija al agregar el producto o al cambiarlo, de modo que
        # un cambio posterior en el menú no altere pedidos ya tomados.
        if detalle.precio_unitario is None or 'producto' in self.changed_data:
            detalle.precio_unitario = detalle.producto.precio
        if commit:
            detalle.save()
        return detalle


class BaseDetallePedidoFormSet(BaseInlineFormSet):
    def clean(self):
        super().clean()
        if any(self.errors):
            return

        productos = set()
        for form in self.forms:
            if self.can_delete and self._should_delete_form(form):
                continue
            producto = form.cleaned_data.get('producto')
            if producto is None:
                continue
            if producto.pk in productos:
                raise ValidationError(
                    f'El producto "{producto.nombre}" está repetido. '
                    'Aumente la cantidad en una sola línea.'
                )
            productos.add(producto.pk)

        if not productos:
            raise ValidationError('Agregue al menos un producto al pedido.')


DetallePedidoFormSet = inlineformset_factory(
    Pedido,
    DetallePedido,
    form=DetallePedidoForm,
    formset=BaseDetallePedidoFormSet,
    extra=1,
    can_delete=True,
)
