from django.core.exceptions import ValidationError


class ErrorCobro(ValidationError):
    """Regla de negocio rechazada, con un mensaje apto para la interfaz."""


class ConsumoInvalidoError(ErrorCobro):
    """Los datos del pedido no permiten determinar un total íntegro y confiable."""


class CobroDuplicadoError(ErrorCobro):
    """La atención ya cuenta con un cobro confirmado."""
