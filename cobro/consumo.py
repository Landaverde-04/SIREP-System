"""Cálculo de consumo independiente del ORM y del catálogo de productos.

La capa de integración debe seleccionar los detalles entregados de una sola
atención y convertirlos en DetalleConsumo usando su precio histórico.
"""

from collections.abc import Iterable
from dataclasses import dataclass
from decimal import Decimal, localcontext


CENTAVO = Decimal('0.01')
CERO = Decimal('0.00')


@dataclass(frozen=True, slots=True)
class DetalleConsumo:
    """Cantidad y precio histórico de una línea, validados e inmutables.

    El precio debe ser Decimal, finito, positivo y expresable en centavos.
    Se permiten ceros decimales adicionales, pero no se redondean precios.
    """

    cantidad: int
    precio_unitario: Decimal

    def __post_init__(self):
        # bool hereda de int, pero no representa una cantidad de productos.
        if isinstance(self.cantidad, bool) or not isinstance(self.cantidad, int):
            raise ValueError('La cantidad debe ser un número entero positivo.')
        if self.cantidad <= 0:
            raise ValueError('La cantidad debe ser mayor que cero.')
        if not isinstance(self.precio_unitario, Decimal):
            raise ValueError('El precio unitario histórico debe ser de tipo Decimal.')
        if not self.precio_unitario.is_finite() or self.precio_unitario <= CERO:
            raise ValueError('El precio unitario histórico debe ser finito y mayor que cero.')

        # Dimensionar la precisión evita que el contexto decimal del llamador
        # redondee importes válidos con muchos dígitos.
        with localcontext() as contexto:
            contexto.prec = max(
                28,
                len(self.precio_unitario.as_tuple().digits),
                self.precio_unitario.adjusted() + 3,
            )
            precio = self.precio_unitario.quantize(CENTAVO)
        if precio != self.precio_unitario:
            raise ValueError('El precio unitario histórico debe ser expresable en centavos.')
        object.__setattr__(self, 'precio_unitario', precio)

    @property
    def subtotal(self) -> Decimal:
        """Importe exacto de la línea, conservando dos posiciones decimales."""
        with localcontext() as contexto:
            contexto.prec = max(
                28,
                len(self.precio_unitario.as_tuple().digits) + len(str(self.cantidad)),
            )
            return self.precio_unitario * self.cantidad


@dataclass(frozen=True, slots=True)
class ConsumoCalculado:
    """Resultado del cálculo: líneas inmutables y total en centavos."""

    detalles: tuple[DetalleConsumo, ...]
    total: Decimal


class ServicioConsumo:
    """Calcula el consumo a partir de detalles previamente seleccionados.

    No selecciona estados, no agrupa por mesa y no consulta precios actuales.
    Acepta cualquier iterable de DetalleConsumo, incluidos generadores.
    """

    def calcular(self, detalles: Iterable[DetalleConsumo]) -> ConsumoCalculado:
        lineas = tuple(detalles)
        if any(not isinstance(detalle, DetalleConsumo) for detalle in lineas):
            raise TypeError('Cada detalle debe ser una instancia de DetalleConsumo.')

        subtotales = tuple(detalle.subtotal for detalle in lineas)
        with localcontext() as contexto:
            contexto.prec = max(
                28,
                max((len(subtotal.as_tuple().digits) for subtotal in subtotales), default=1)
                + len(str(len(subtotales))),
            )
            total = sum(subtotales, CERO)
        return ConsumoCalculado(detalles=lineas, total=total)
