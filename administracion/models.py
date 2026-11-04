import re

from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models

from core.models import ModeloBase


class Mesa(ModeloBase):
    """
    Mesa física del restaurante.

    No guarda un campo "estado": que una mesa esté ocupada se deduce de si
    tiene una Atención abierta (ver reservaciones.Atencion). Así el estado no
    puede quedar desincronizado. El campo heredado ``activo`` indica si la
    mesa puede ofrecerse (una mesa deshabilitada no se reserva ni se asigna).
    """

    numero = models.PositiveSmallIntegerField('número', unique=True)
    capacidad = models.PositiveSmallIntegerField(
        'capacidad', validators=[MinValueValidator(1)],
        help_text='Cantidad máxima de personas.',
    )
    ubicacion = models.CharField('ubicación', max_length=60, blank=True)

    class Meta:
        verbose_name = 'mesa'
        verbose_name_plural = 'mesas'
        ordering = ['numero']

    def __str__(self):
        return f'Mesa {self.numero}'

    def admite(self, cantidad_personas):
        """RN-02: la capacidad debe ser igual o mayor a la cantidad de personas."""
        return self.capacidad >= cantidad_personas

    @property
    def atencion_abierta(self):
        """Atención en curso de la mesa, o None si está libre."""
        return self.atenciones.filter(estado='ABIERTA').first()

    @property
    def esta_ocupada(self):
        return self.atenciones.filter(estado='ABIERTA').exists()


TELEFONO_PATRON = re.compile(r'^(?:\+?503)?([267]\d{3})(\d{4})$')


def normalizar_telefono(valor):
    """
    Devuelve el teléfono con formato ``####-####`` o lanza ValidationError.

    Acepta números de El Salvador de ocho dígitos que empiezan con 2, 6 o 7,
    con o sin guion, espacios o prefijo +503.
    """
    limpio = re.sub(r'[\s\-().]', '', valor or '')
    coincidencia = TELEFONO_PATRON.match(limpio)
    if not coincidencia:
        raise ValidationError(
            'Ingrese un teléfono válido de 8 dígitos que empiece con 2, 6 o 7 (por ejemplo 7777-8888).',
            code='telefono_invalido',
        )
    return f'{coincidencia.group(1)}-{coincidencia.group(2)}'


CONECTORES_NOMBRE = {'de', 'del', 'la', 'las', 'los', 'y', 'e', 'van', 'von', 'da', 'di'}


def normalizar_nombre(valor):
    """
    Escribe el nombre con mayúscula inicial en cada palabra y quita espacios
    sobrantes: "  ana   lÓPEZ de la o " -> "Ana López de la O".
    Los conectores (de, del, la, y...) quedan en minúscula salvo al inicio.
    """
    palabras = (valor or '').split()
    resultado = []
    for posicion, palabra in enumerate(palabras):
        minuscula = palabra.lower()
        if posicion > 0 and minuscula in CONECTORES_NOMBRE:
            resultado.append(minuscula)
        else:
            resultado.append('-'.join(parte[:1].upper() + parte[1:] for parte in minuscula.split('-')))
    return ' '.join(resultado)


class Cliente(ModeloBase):
    """
    Cliente del restaurante. El anfitrión puede registrarlo rápidamente
    (nombre y teléfono) desde una reservación o un ingreso (CU-04); la gestión
    completa de sus datos corresponde al módulo de administración.
    """

    nombre = models.CharField('nombre', max_length=120)
    telefono = models.CharField('teléfono', max_length=9, unique=True,
                                error_messages={'unique': 'Ya existe un cliente con ese teléfono.'})

    class Meta:
        verbose_name = 'cliente'
        verbose_name_plural = 'clientes'
        ordering = ['nombre']

    def __str__(self):
        return f'{self.nombre} ({self.telefono})'

    def clean(self):
        super().clean()
        self.nombre = normalizar_nombre(self.nombre)
        if not self.nombre:
            raise ValidationError({'nombre': 'Ingrese el nombre del cliente.'})
        try:
            self.telefono = normalizar_telefono(self.telefono)
        except ValidationError as error:
            raise ValidationError({'telefono': error.messages})

    def save(self, *args, **kwargs):
        # También se normaliza al guardar desde el admin, la consola o los datos de prueba.
        self.nombre = normalizar_nombre(self.nombre)
        super().save(*args, **kwargs)
