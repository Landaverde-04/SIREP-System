from decimal import Decimal

from django import forms

from .pagos import FormaPago, validar_pago


class RegistrarCobroForm(forms.Form):
    forma_pago = forms.ChoiceField(
        label='Forma de pago', choices=FormaPago.choices,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    monto_recibido = forms.DecimalField(
        label='Monto recibido', max_digits=14, decimal_places=2, min_value=Decimal('0.01'),
        widget=forms.NumberInput(attrs={
            'class': 'form-control', 'step': '0.01', 'min': '0.01', 'inputmode': 'decimal',
            'aria-describedby': 'ayuda-monto',
        }),
    )
    confirmar = forms.BooleanField(
        label='Confirmo el pago completo y el cierre de esta atención.',
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )

    def __init__(self, *args, total=None, **kwargs):
        self.total = total
        super().__init__(*args, **kwargs)
        self.fields['forma_pago'].initial = FormaPago.EFECTIVO
        if total is not None:
            self.fields['monto_recibido'].initial = total

    def clean(self):
        datos = super().clean()
        if self.total is not None and 'monto_recibido' in datos and 'forma_pago' in datos:
            validar_pago(self.total, datos['monto_recibido'], datos['forma_pago'])
        return datos
