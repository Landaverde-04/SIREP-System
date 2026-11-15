from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from administracion.models import Cliente
from .agenda import LineaDeTiempo, proxima_media_hora
from .forms import (
    BuscarReservacionForm, CancelarReservacionForm, ClienteRapidoForm, DisponibilidadForm, IngresoForm,
    PeriodoForm, ReservacionForm,
)
from .models import Atencion, Reservacion, formatear_digitos
from .servicios import (
    MesaNoDisponibleError, ServicioDisponibilidad, ServicioIngreso, ServicioReservaciones,
)


def _obtener_reservacion(codigo):
    return get_object_or_404(Reservacion.objects.select_related('cliente', 'mesa'), codigo=codigo)


def _mesas_del_formulario(form, disponibilidad, excluir_reservacion=None):
    """Mesas disponibles para el período del formulario, o None si aún no es válido."""
    datos = getattr(form, 'cleaned_data', {})
    if 'inicio' not in datos or 'cantidad_personas' not in datos:
        return None
    return list(disponibilidad.mesas_disponibles(
        datos['inicio'], datos['duracion'], datos['cantidad_personas'], excluir_reservacion))


# --- CU-07 Buscar reservación / listado ---------------------------------------

@login_required
@permission_required('reservaciones.view_reservacion', raise_exception=True)
def lista_reservaciones(request):
    form = BuscarReservacionForm(request.GET or None)
    reservaciones = Reservacion.objects.select_related('cliente', 'mesa')
    filtrando = form.is_bound and form.is_valid() and any(form.cleaned_data.values())
    if filtrando:
        datos = form.cleaned_data
        reservaciones = reservaciones.buscar(datos['q'])
        if datos['fecha']:
            reservaciones = reservaciones.del_dia(datos['fecha'])
        if datos['estado']:
            reservaciones = reservaciones.filter(estado=datos['estado'])
    else:
        # Por defecto: las reservaciones programadas desde hoy en adelante.
        reservaciones = reservaciones.programadas().filter(
            fecha_hora_inicio__date__gte=timezone.localdate())
    return render(request, 'reservaciones/lista_reservaciones.html', {
        'form': form,
        'reservaciones': reservaciones.order_by('fecha_hora_inicio')[:200],
        'filtrando': filtrando,
    })


@login_required
@permission_required('reservaciones.view_reservacion', raise_exception=True)
def detalle_reservacion(request, codigo):
    reservacion = _obtener_reservacion(codigo)
    atencion = getattr(reservacion, 'atencion', None)  # None si aún no se registra el ingreso
    return render(request, 'reservaciones/detalle_reservacion.html', {
        'reservacion': reservacion,
        'atencion': atencion,
        'es_de_hoy': timezone.localdate(reservacion.fecha_hora_inicio) == timezone.localdate(),
    })


# --- CU-02 Consultar disponibilidad -------------------------------------------

@login_required
@permission_required('reservaciones.view_reservacion', raise_exception=True)
def consultar_disponibilidad(request):
    """
    Mapa de mesas para el período consultado y agenda del día. Sin parámetros
    muestra la próxima media hora de hoy, para ver de inmediato cómo está el salón.
    """
    disponibilidad = ServicioDisponibilidad()
    if 'fecha' in request.GET:
        form = DisponibilidadForm(request.GET, disponibilidad=disponibilidad)
    else:
        inicio = proxima_media_hora(disponibilidad.ahora)
        form = DisponibilidadForm({'fecha': inicio.date().isoformat(), 'hora': inicio.strftime('%H:%M'),
                                   'duracion_horas': '2', 'cantidad_personas': ''},
                                  disponibilidad=disponibilidad)

    contexto = {'form': form}
    if form.is_valid():
        datos = form.cleaned_data
        inicio, duracion, personas = datos['inicio'], datos['duracion'], datos.get('cantidad_personas')
        estados = disponibilidad.estado_mesas(inicio, duracion, personas)
        zonas = {}
        for estado in estados:
            zonas.setdefault(estado.mesa.ubicacion or 'Sin ubicación', []).append(estado)
        conteo = {clave: sum(1 for e in estados if e.estado == clave)
                  for clave in ('libre', 'reservada', 'ocupada', 'pequena')}
        reservaciones, atenciones = disponibilidad.agenda_del_dia(datos['fecha'])
        parametros = {'fecha': datos['fecha'].isoformat(), 'hora': datos['hora'].strftime('%H:%M'),
                      'duracion_horas': str(datos['duracion_horas']).rstrip('0').rstrip('.')}
        if personas:
            parametros['cantidad_personas'] = personas
        contexto.update({
            'zonas': zonas.items(),
            'conteo': conteo,
            'total': len(estados),
            'inicio': inicio,
            'fin': inicio + duracion,
            'personas': personas,
            'parametros': urlencode(parametros),
            'agenda': LineaDeTiempo(datos['fecha'], [e.mesa for e in sorted(estados, key=lambda e: e.mesa.numero)],
                                    reservaciones, atenciones, periodo=(inicio, inicio + duracion),
                                    ahora=disponibilidad.ahora),
        })
    return render(request, 'reservaciones/disponibilidad.html', contexto)


# --- CU-01 Registrar reservación ----------------------------------------------

@login_required
@permission_required('reservaciones.add_reservacion', raise_exception=True)
def crear_reservacion(request):
    disponibilidad = ServicioDisponibilidad()
    if request.method == 'POST':
        form = ReservacionForm(request.POST, disponibilidad=disponibilidad)
    elif 'fecha' in request.GET and request.GET.get('cantidad_personas'):
        # Viene de la consulta de disponibilidad con los datos ya ingresados.
        form = ReservacionForm(request.GET, disponibilidad=disponibilidad)
    elif 'fecha' in request.GET:
        # Viene del mapa sin cantidad de personas: se precargan los datos y la mesa elegida.
        form = ReservacionForm(initial=request.GET.dict(), disponibilidad=disponibilidad)
    else:
        form = ReservacionForm(disponibilidad=disponibilidad)

    mesas = None
    if form.is_bound:
        valido = form.is_valid()
        if valido and form.confirmando:
            datos = form.cleaned_data
            try:
                reservacion = ServicioReservaciones(request.user, disponibilidad).registrar(
                    cliente=datos['cliente'], mesa=datos['mesa'], inicio=datos['inicio'],
                    duracion=datos['duracion'], cantidad_personas=datos['cantidad_personas'],
                )
            except MesaNoDisponibleError as error:
                form.add_error('mesa', error)
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(
                    request,
                    f'Reservación {reservacion.codigo} registrada para el '
                    f'{timezone.localtime(reservacion.fecha_hora_inicio):%d/%m/%Y a las %H:%M}, '
                    f'mesa {reservacion.mesa.numero}, {reservacion.cantidad_personas} personas.',
                )
                return redirect('reservaciones:detalle_reservacion', codigo=reservacion.codigo)
        mesas = _mesas_del_formulario(form, disponibilidad)

    return render(request, 'reservaciones/form_reservacion.html', {
        'form': form,
        'mesas': mesas,
        'cliente_seleccionado': _cliente_del_formulario(form),
        'titulo': 'Nueva reservación',
    })


def _cliente_del_formulario(form):
    if not form.is_bound or 'cliente' not in form.fields:
        return None
    datos = getattr(form, 'cleaned_data', {})
    if datos.get('cliente'):
        return datos['cliente']
    valor = form.data.get('cliente')
    if valor and str(valor).isdigit():
        return Cliente.objects.filter(pk=valor, activo=True).first()
    return None


# --- CU-05 Modificar reservación ----------------------------------------------

@login_required
@permission_required('reservaciones.change_reservacion', raise_exception=True)
def modificar_reservacion(request, codigo):
    reservacion = _obtener_reservacion(codigo)
    if not reservacion.esta_programada:
        messages.warning(request, 'Solo pueden modificarse reservaciones programadas. '
                                  f'Esta reservación está {reservacion.get_estado_display().lower()}.')
        return redirect('reservaciones:detalle_reservacion', codigo=codigo)

    disponibilidad = ServicioDisponibilidad()
    if request.method == 'POST':
        datos_form = request.POST
    else:
        # Se muestran los datos actuales y, de una vez, las mesas libres para ellos.
        datos_form = {**PeriodoForm.iniciales_desde(reservacion), 'mesa': reservacion.mesa_id,
                      'accion': 'consultar'}
    form = ReservacionForm(datos_form, disponibilidad=disponibilidad, pedir_cliente=False)

    valido = form.is_valid()
    if request.method == 'POST' and valido and form.confirmando:
        datos = form.cleaned_data
        try:
            reservacion = ServicioReservaciones(request.user, disponibilidad).modificar(
                reservacion, mesa=datos['mesa'], inicio=datos['inicio'], duracion=datos['duracion'],
                cantidad_personas=datos['cantidad_personas'],
            )
        except MesaNoDisponibleError as error:
            form.add_error('mesa', error)
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f'Reservación {reservacion.codigo} modificada correctamente.')
            return redirect('reservaciones:detalle_reservacion', codigo=reservacion.codigo)

    mesas = _mesas_del_formulario(form, disponibilidad, excluir_reservacion=reservacion)
    return render(request, 'reservaciones/form_reservacion.html', {
        'form': form,
        'mesas': mesas,
        'reservacion': reservacion,
        'mesa_asignada_libre': mesas is not None and reservacion.mesa in mesas,
        'titulo': f'Modificar reservación {reservacion.codigo}',
    })


# --- CU-06 Cancelar reservación -----------------------------------------------

@login_required
@permission_required('reservaciones.cancelar_reservacion', raise_exception=True)
def cancelar_reservacion(request, codigo):
    reservacion = _obtener_reservacion(codigo)
    if not reservacion.esta_programada:
        messages.warning(request, 'Solo pueden cancelarse reservaciones programadas. '
                                  f'Esta reservación está {reservacion.get_estado_display().lower()}.')
        return redirect('reservaciones:detalle_reservacion', codigo=codigo)

    form = CancelarReservacionForm(request.POST or None)
    if request.method == 'POST' and form.is_valid():
        try:
            ServicioReservaciones(request.user).cancelar(reservacion, form.cleaned_data['motivo'])
        except ValidationError as error:
            form.add_error(None, error)
        else:
            messages.success(request, f'Reservación {reservacion.codigo} cancelada. '
                                      f'La mesa {reservacion.mesa.numero} queda disponible en ese período.')
            return redirect('reservaciones:detalle_reservacion', codigo=codigo)
    return render(request, 'reservaciones/cancelar_reservacion.html', {
        'reservacion': reservacion, 'form': form,
    })


# --- CU-03 Registrar ingreso y asignar mesa -----------------------------------

@login_required
@permission_required('reservaciones.add_atencion', raise_exception=True)
def panel_ingresos(request):
    hoy = timezone.localdate()
    q = request.GET.get('q', '').strip()
    reservaciones = (Reservacion.objects.programadas().del_dia(hoy)
                     .select_related('cliente', 'mesa').buscar(q).order_by('fecha_hora_inicio'))
    atenciones = Atencion.objects.abiertas().select_related('mesa', 'cliente', 'reservacion') \
        .order_by('mesa__numero')
    return render(request, 'reservaciones/panel_ingresos.html', {
        'reservaciones': reservaciones,
        'atenciones': atenciones,
        'q': q,
        'hoy': hoy,
    })


@login_required
@permission_required('reservaciones.add_atencion', raise_exception=True)
def ingreso_con_reservacion(request, codigo):
    reservacion = _obtener_reservacion(codigo)
    if not reservacion.esta_programada:
        messages.warning(request, f'La reservación {codigo} no está programada '
                                  f'({reservacion.get_estado_display().lower()}); '
                                  'puede registrar el ingreso como cliente sin reservación.')
        return redirect('reservaciones:panel_ingresos')

    servicio = ServicioIngreso(request.user)
    if request.method == 'POST':
        form = IngresoForm(request.POST)
    else:
        form = IngresoForm({'cantidad_personas': reservacion.cantidad_personas, 'accion': 'consultar'})

    problema, alternativas = None, None
    if form.is_valid():
        personas = form.cleaned_data['cantidad_personas']
        problema = servicio.problema_con_mesa_reservada(reservacion, personas)
        if problema:
            alternativas = list(servicio.mesas_para_ingreso(
                personas, reservacion.duracion_estimada, reservacion=reservacion))

        if request.method == 'POST' and form.confirmando and (not problema or form.exigir_mesa()):
            try:
                atencion = servicio.registrar_con_reservacion(
                    reservacion, personas, mesa=form.cleaned_data['mesa'] if problema else None)
            except MesaNoDisponibleError as error:
                form.add_error('mesa', error)
                alternativas = list(servicio.mesas_para_ingreso(
                    personas, reservacion.duracion_estimada, reservacion=reservacion))
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, f'Ingreso registrado: mesa {atencion.mesa.numero} ocupada '
                                          f'por {atencion.cantidad_personas} personas. '
                                          f'Reservación {reservacion.codigo} atendida.')
                return redirect('reservaciones:panel_ingresos')

    return render(request, 'reservaciones/ingreso_reservacion.html', {
        'reservacion': reservacion, 'form': form, 'problema': problema, 'mesas': alternativas,
    })


@login_required
@permission_required('reservaciones.add_atencion', raise_exception=True)
def ingreso_sin_reservacion(request):
    servicio = ServicioIngreso(request.user)
    form = IngresoForm(request.POST or None)
    mesas = None
    if form.is_bound and form.is_valid():
        personas = form.cleaned_data['cantidad_personas']
        mesas = list(servicio.mesas_para_ingreso(personas))
        if form.confirmando and form.exigir_mesa():
            try:
                atencion = servicio.registrar_sin_reservacion(
                    form.cleaned_data['mesa'], personas, cliente=form.cleaned_data['cliente'])
            except MesaNoDisponibleError as error:
                form.add_error('mesa', error)
                mesas = list(servicio.mesas_para_ingreso(personas))
            except ValidationError as error:
                form.add_error(None, error)
            else:
                messages.success(request, f'Ingreso registrado: mesa {atencion.mesa.numero} ocupada '
                                          f'por {atencion.cantidad_personas} personas.')
                return redirect('reservaciones:panel_ingresos')

    return render(request, 'reservaciones/ingreso_sin_reservacion.html', {
        'form': form, 'mesas': mesas, 'cliente_seleccionado': _cliente_del_formulario(form),
    })


# --- CU-04 Registrar cliente nuevo (desde reservación o ingreso) --------------

def _puede_operar_reservaciones(user):
    return user.has_perm('reservaciones.add_reservacion') or \
        user.has_perm('reservaciones.change_reservacion') or \
        user.has_perm('reservaciones.add_atencion')


def _cliente_json(cliente):
    return {'id': cliente.pk, 'nombre': cliente.nombre, 'telefono': cliente.telefono}


@login_required
@require_GET
def buscar_clientes(request):
    if not _puede_operar_reservaciones(request.user):
        raise PermissionDenied
    texto = request.GET.get('q', '').strip()
    if len(texto) < 2:
        return JsonResponse({'clientes': []})
    condicion = Q(nombre__icontains=texto)
    digitos = ''.join(c for c in texto if c.isdigit())
    if len(digitos) >= 3:
        condicion |= Q(telefono__contains=formatear_digitos(digitos))
    clientes = Cliente.objects.filter(activo=True).filter(condicion).order_by('nombre')[:10]
    return JsonResponse({'clientes': [_cliente_json(c) for c in clientes]})


@login_required
@require_POST
def registrar_cliente(request):
    if not (request.user.has_perm('administracion.add_cliente') and _puede_operar_reservaciones(request.user)):
        return JsonResponse({'error': 'No tiene permiso para registrar clientes.'}, status=403)
    form = ClienteRapidoForm(request.POST)
    if not form.is_valid():
        return JsonResponse({'errores': {campo: [str(m) for m in lista]
                                         for campo, lista in form.errors.items()}}, status=400)
    existente = Cliente.objects.filter(telefono=form.cleaned_data['telefono']).first()
    if existente:
        # CU-04 6a: se pregunta si es la misma persona en lugar de duplicarla.
        return JsonResponse({'existe': True, 'cliente': _cliente_json(existente)})
    cliente = form.save()
    return JsonResponse({'creado': True, 'cliente': _cliente_json(cliente)}, status=201)
