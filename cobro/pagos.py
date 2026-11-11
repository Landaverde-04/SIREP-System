"""Reglas de registro de pagos; no ejecuta transacciones financieras externas."""

from decimal import Decimal

from django.core.exceptions import ValidationError
from django.core.validators import DecimalValidator
from django.db import models


class FormaPago(models.TextChoices):
    EFECTIVO = 'EFECTIVO', 'Efectivo'
    TARJETA = 'TARJETA', 'Tarjeta'
    OTRO = 'OTRO', 'Otro medio'


def validar_importe(importe, campo):
    """Exige Decimal positivo, finito y de hasta 14 dígitos y dos decimales."""
    if not isinstance(importe, Decimal) or not importe.is_finite() or importe <= 0:
        raise ValidationError({campo: 'Ingrese un importe decimal válido y mayor que cero.'})
    try:
        DecimalValidator(max_digits=14, decimal_places=2)(importe)
    except ValidationError as error:
        raise ValidationError({campo: error.messages}) from error


def validar_pago(total, monto_recibido, forma_pago):
    """Valida cobro completo y devuelve el cambio; solo efectivo admite excedente."""
    validar_importe(total, 'total')
    validar_importe(monto_recibido, 'monto_recibido')
    if forma_pago not in FormaPago.values:
        raise ValidationError({'forma_pago': 'Seleccione una forma de pago válida.'})
    if monto_recibido < total:
        raise ValidationError({'monto_recibido': 'El monto recibido no cubre el total del consumo.'})
    if forma_pago != FormaPago.EFECTIVO and monto_recibido != total:
        raise ValidationError({'monto_recibido': 'Para este medio, registre el monto exacto del total.'})
    return monto_recibido - total
