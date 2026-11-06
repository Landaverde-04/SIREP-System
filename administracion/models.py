"""
Módulo de Administración (Waldo): catálogo del restaurante.

Clases del diagrama de clases conceptual de la Etapa 1:
Mesa, CategoriaProducto, Producto y Cliente.

Convenciones para los demás módulos:
  - Todas heredan de core.ModeloBase, por lo que el campo ``activo`` indica si
    el registro está habilitado. Nada se elimina: se deshabilita (CU-19, CU-23).
  - Mesa.objects.disponibles()  -> mesas habilitadas y libres (reservaciones).
  - Producto.objects.ofertables() -> habilitados y disponibles (RN-06, pedidos).
"""
import re

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.db.models.functions import Lower

from core.models import ModeloBase


# ---------------------------------------------------------------- Mesa

class MesaQuerySet(models.QuerySet):
    def habilitadas(self):
        return self.filter(activo=True)

    def disponibles(self):
        return self.filter(activo=True, estado=Mesa.Estado.DISPONIBLE)


class Mesa(ModeloBase):
    class Estado(models.TextChoices):
        DISPONIBLE = 'disponible', 'Disponible'
        RESERVADA = 'reservada', 'Reservada'
        OCUPADA = 'ocupada', 'Ocupada'
        DESHABILITADA = 'deshabilitada', 'Deshabilitada'

    numero = models.PositiveIntegerField(
        'número', unique=True, validators=[MinValueValidator(1)],
        error_messages={'unique': 'Ya existe una mesa con ese número.'},
    )
    capacidad = models.PositiveSmallIntegerField(
        validators=[MinValueValidator(1)],
        help_text='Cantidad máxima de personas.',
    )
    ubicacion = models.CharField('ubicación', max_length=80, blank=True)
    estado = models.CharField(
        max_length=15, choices=Estado.choices, default=Estado.DISPONIBLE,
    )

    objects = MesaQuerySet.as_manager()

    class Meta:
        ordering = ['numero']
        verbose_name = 'mesa'
        verbose_name_plural = 'mesas'

    def __str__(self):
        return f'Mesa {self.numero}'

    @property
    def habilitada(self):
        return self.activo

    def deshabilitar(self):
        """CU-19. No se permite si la mesa está en uso o apartada."""
        if self.estado in (self.Estado.OCUPADA, self.Estado.RESERVADA):
            raise ValidationError(
                f'No se puede deshabilitar la {self}: está '
                f'{self.get_estado_display().lower()}.'
            )
        self.activo = False
        self.estado = self.Estado.DESHABILITADA
        self.save(update_fields=['activo', 'estado', 'fecha_modificacion'])

    def habilitar(self):
        self.activo = True
        self.estado = self.Estado.DISPONIBLE
        self.save(update_fields=['activo', 'estado', 'fecha_modificacion'])


# ------------------------------------------------- CategoriaProducto

class CategoriaProducto(ModeloBase):
    nombre = models.CharField(
        max_length=60, unique=True,
        error_messages={'unique': 'Ya existe una categoría con ese nombre.'},
    )

    class Meta:
        ordering = ['nombre']
        verbose_name = 'categoría de producto'
        verbose_name_plural = 'categorías de producto'

    def __str__(self):
        return self.nombre


# ------------------------------------------------------------ Producto

class ProductoQuerySet(models.QuerySet):
    def habilitados(self):
        return self.filter(activo=True)

    def ofertables(self):
        """Productos que pueden pedirse: habilitados y disponibles (RN-06)."""
        return self.filter(activo=True, disponible=True)


class Producto(ModeloBase):
    nombre = models.CharField(max_length=100)
    descripcion = models.TextField('descripción', blank=True)
    precio = models.DecimalField(
        max_digits=8, decimal_places=2,
        validators=[MinValueValidator(0.01)],
    )
    categoria = models.ForeignKey(
        CategoriaProducto, on_delete=models.PROTECT,
        related_name='productos', verbose_name='categoría',
    )
    disponible = models.BooleanField(
        default=True,
        help_text='Se desmarca temporalmente cuando se agotan los ingredientes.',
    )

    objects = ProductoQuerySet.as_manager()

    class Meta:
        ordering = ['categoria__nombre', 'nombre']
        verbose_name = 'producto'
        verbose_name_plural = 'productos'
        constraints = [
            models.UniqueConstraint(
                Lower('nombre'),
                name='producto_nombre_unico_ci',
                violation_error_message='Ya existe un producto con ese nombre.',
            ),
        ]

    def __str__(self):
        return self.nombre

    @property
    def habilitado(self):
        return self.activo

    def alternar_disponibilidad(self):
        """CU-22: disponible <-> no disponible."""
        self.disponible = not self.disponible
        self.save(update_fields=['disponible', 'fecha_modificacion'])

    def deshabilitar(self):
        """CU-23: deja de ofrecerse, sin borrar el historial."""
        self.activo = False
        self.save(update_fields=['activo', 'fecha_modificacion'])

    def habilitar(self):
        self.activo = True
        self.save(update_fields=['activo', 'fecha_modificacion'])


# ------------------------------------------------------------- Cliente

TELEFONO_RE = re.compile(r'^\+?\d[\d \-]{6,14}\d$')


def validar_telefono(valor):
    if not TELEFONO_RE.match(valor or ''):
        raise ValidationError(
            'Ingresa un teléfono válido (solo números, espacios o guiones; '
            'puede iniciar con +).'
        )


class Cliente(ModeloBase):
    nombre = models.CharField(max_length=120)
    telefono = models.CharField(
        'teléfono', max_length=20, unique=True, validators=[validar_telefono],
        error_messages={'unique': 'Ya existe un cliente con ese teléfono.'},
    )

    class Meta:
        ordering = ['nombre']
        verbose_name = 'cliente'
        verbose_name_plural = 'clientes'

    def __str__(self):
        return f'{self.nombre} ({self.telefono})'
