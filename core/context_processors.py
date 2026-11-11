from .navegacion import modulos_disponibles


def navegacion(request):
    modulos = modulos_disponibles(request.user)
    coincidencia = request.resolver_match
    activo = ''
    if coincidencia:
        activo = coincidencia.kwargs.get('modulo') or coincidencia.app_name
    seleccionado = next((item for item in modulos if item['clave'] == activo), None)
    return {'modulos_navegacion': modulos, 'modulo_actual': activo, 'modulo_navegacion': seleccionado}
