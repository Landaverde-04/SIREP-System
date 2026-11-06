from django import forms

from .models import Mesa, CategoriaProducto, Producto, Cliente


class _BootstrapMixin:
    """Aplica las clases de Bootstrap a los widgets del formulario."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            w = campo.widget
            if isinstance(w, forms.CheckboxInput):
                w.attrs.setdefault('class', 'form-check-input')
            elif isinstance(w, forms.Select):
                w.attrs.setdefault('class', 'form-select')
            else:
                w.attrs.setdefault('class', 'form-control')


class MesaForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Mesa
        fields = ('numero', 'capacidad', 'ubicacion')
        labels = {'numero': 'Número de mesa'}
        widgets = {
            'ubicacion': forms.TextInput(attrs={'placeholder': 'Ej: Terraza, ventana'}),
        }


class CategoriaForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = CategoriaProducto
        fields = ('nombre',)
        widgets = {
            'nombre': forms.TextInput(attrs={'placeholder': 'Ej: Entradas, Bebidas'}),
        }

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        duplicada = CategoriaProducto.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            duplicada = duplicada.exclude(pk=self.instance.pk)
        if duplicada.exists():
            raise forms.ValidationError('Ya existe una categoría con ese nombre.')
        return nombre


class ProductoForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Producto
        fields = ('nombre', 'descripcion', 'precio', 'categoria', 'disponible')
        widgets = {
            'descripcion': forms.Textarea(attrs={'rows': 3}),
            'precio': forms.NumberInput(attrs={'step': '0.01', 'min': '0.01'}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Solo categorías habilitadas (más la actual del producto al editar).
        qs = CategoriaProducto.objects.filter(activo=True)
        if self.instance.pk:
            qs = CategoriaProducto.objects.filter(activo=True) | \
                CategoriaProducto.objects.filter(pk=self.instance.categoria_id)
        self.fields['categoria'].queryset = qs.distinct()
        self.fields['categoria'].empty_label = 'Selecciona una categoría'

    def clean_nombre(self):
        nombre = self.cleaned_data['nombre'].strip()
        duplicado = Producto.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            duplicado = duplicado.exclude(pk=self.instance.pk)
        if duplicado.exists():
            raise forms.ValidationError('Ya existe un producto con ese nombre.')
        return nombre


class ClienteForm(_BootstrapMixin, forms.ModelForm):
    class Meta:
        model = Cliente
        fields = ('nombre', 'telefono')
        widgets = {
            'telefono': forms.TextInput(attrs={'placeholder': 'Ej: 7000-0000'}),
        }

    def clean_nombre(self):
        return ' '.join(self.cleaned_data['nombre'].split())

    def clean_telefono(self):
        return self.cleaned_data['telefono'].strip()
