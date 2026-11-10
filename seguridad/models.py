from django.contrib.auth.models import AbstractUser
from django.db import models
from django.core.validators import MinValueValidator

from core.models import ModeloBase


class Usuario(AbstractUser):
    """
    Modelo de usuario del sistema. Extiende AbstractUser de Django,
    que ya provee: username, password, email, first_name, last_name,
    is_active, date_joined, last_login, groups y permissions.

    No hereda ModeloBase porque AbstractUser ya cubre esos campos.
    """

    debe_cambiar_password = models.BooleanField(default=False)

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'


class Empleado(ModeloBase):
    nombres = models.CharField(max_length=100)
    apellidos = models.CharField(max_length=100)
    cargo = models.CharField(max_length=100)
    telefono = models.CharField('teléfono', max_length=20, blank=True)
    correo = models.EmailField('correo electrónico', blank=True)
    fecha_ingreso = models.DateField('fecha de ingreso')
    salario_mensual = models.DecimalField(
        'salario mensual', max_digits=10, decimal_places=2, blank=True, null=True,
        validators=[MinValueValidator(0)],
    )

    class Meta:
        verbose_name = 'empleado'
        verbose_name_plural = 'empleados'
        ordering = ['nombres', 'apellidos', 'pk']
        constraints = [
            models.CheckConstraint(
                condition=models.Q(salario_mensual__gte=0) | models.Q(salario_mensual__isnull=True),
                name='empleado_salario_no_negativo',
            ),
        ]

    @property
    def codigo(self):
        # El identificador de la base garantiza códigos únicos sin contadores propios.
        return f'EMP-{self.pk:06d}' if self.pk is not None else ''

    def __str__(self):
        return f'{self.nombres} {self.apellidos}'
