from unittest.mock import patch

from django.db import OperationalError
from django.test import TestCase
from django.urls import reverse


class EstadoServicioTests(TestCase):
    def test_responde_sin_autenticacion_y_sin_cache(self):
        respuesta = self.client.get(reverse('core:estado_servicio'))
        self.assertContains(respuesta, 'OK')
        self.assertIn('no-store', respuesta.headers['Cache-Control'])

    def test_falla_de_postgresql_devuelve_503(self):
        with patch('core.views.connection.cursor', side_effect=OperationalError('Error de conexión')):
            respuesta = self.client.get(reverse('core:estado_servicio'))
        self.assertContains(respuesta, 'No disponible', status_code=503)
