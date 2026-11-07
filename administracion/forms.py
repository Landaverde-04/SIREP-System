from django import forms
from django.core.exceptions import ValidationError

from .models import CategoriaProducto, Cliente, Mesa, Producto, normalizar_nombre, normalizar_telefono


class FormularioBootstrap(forms.ModelForm):
    """Agrega las clases de Bootstrap y resalta los campos con error."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for campo in self.fields.values():
            if isinstance(campo.widget, forms.CheckboxInput):
                campo.widget.attrs.setdefault('class', 'form-check-input')
            elif isinstance(campo.widget, forms.Select):
                campo.widget.attrs.setdefault('class', 'form-select')
            else:
                campo.widget.attrs.setdefault('class', 'form-control')

    def add_error(self, field, error):
        super().add_error(field, error)
        for nombre in self.errors:
            if nombre in self.fields:
                attrs = self.fields[nombre].widget.attrs
                if 'is-invalid' not in attrs.get('class', ''):
                    attrs['class'] = (attrs.get('class', '') + ' is-invalid').strip()


class MesaForm(FormularioBootstrap):
    """CU-17 Registrar mesa y CU-18 Modificar mesa."""

    class Meta:
        model = Mesa
        fields = ['numero', 'capacidad', 'ubicacion']
        labels = {'numero': 'Número de mesa', 'capacidad': 'Capacidad (personas)', 'ubicacion': 'Ubicación'}
        help_texts = {'ubicacion': 'Por ejemplo: Ventana, Terraza, Salón principal.'}
        widgets = {
            'numero': forms.NumberInput(attrs={'min': 1}),
            'capacidad': forms.NumberInput(attrs={'min': 1, 'max': 50}),
            'ubicacion': forms.TextInput(attrs={'list': 'ubicaciones', 'autocomplete': 'off'}),
        }
        error_messages = {
            'numero': {'unique': 'Ya existe una mesa con ese número.'},
        }

    def clean_numero(self):
        numero = self.cleaned_data['numero']
        if numero is not None and numero < 1:
            raise ValidationError('El número de mesa debe ser mayor que cero.')
        return numero

    def clean_capacidad(self):
        capacidad = self.cleaned_data['capacidad']
        if capacidad is None:
            return capacidad
        if not 1 <= capacidad <= 50:
            raise ValidationError('La capacidad debe estar entre 1 y 50 personas.')
        if self.instance.pk:
            requerida = self.instance.capacidad_minima_requerida()
            if capacidad < requerida:
                raise ValidationError(
                    f'La mesa tiene reservaciones programadas para {requerida} personas. '
                    'Asígneles otra mesa antes de reducir la capacidad.')
        return capacidad

    def clean_ubicacion(self):
        return ' '.join((self.cleaned_data.get('ubicacion') or '').split()).capitalize()


class ClienteForm(FormularioBootstrap):
    """Registro y CU-25 Modificar cliente."""

    telefono = forms.CharField(label='Teléfono', max_length=9,
                               widget=forms.TextInput(attrs={'placeholder': '7777-8888', 'inputmode': 'numeric',
                                                             'data-telefono': '1', 'autocomplete': 'off'}),
                               help_text='8 dígitos; el guion se agrega solo.')

    class Meta:
        model = Cliente
        fields = ['nombre', 'telefono', 'activo']
        labels = {'nombre': 'Nombre completo', 'activo': 'Cliente activo (aparece al buscar en reservaciones)'}
        widgets = {'nombre': forms.TextInput(attrs={'data-nombre': '1', 'autocomplete': 'off'})}
        error_messages = {'telefono': {'unique': 'Ya existe un cliente con ese teléfono.'}}

    def clean_nombre(self):
        nombre = normalizar_nombre(self.cleaned_data['nombre'])
        if not nombre:
            raise ValidationError('Ingrese el nombre del cliente.')
        return nombre

    def clean_telefono(self):
        telefono = normalizar_telefono(self.cleaned_data['telefono'])
        repetido = Cliente.objects.filter(telefono=telefono).exclude(pk=self.instance.pk).first()
        if repetido:
            raise ValidationError(f'Ya existe un cliente con ese teléfono: {repetido.nombre}.')
        return telefono


class CategoriaForm(FormularioBootstrap):
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


class ProductoForm(FormularioBootstrap):
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
