from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.exceptions import ValidationError
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from pedidos.models import Pedido
from reservaciones.models import Atencion

from .excepciones import CobroDuplicadoError, ConsumoInvalidoError
from .forms import RegistrarCobroForm
from .integracion import AdaptadorConsumoPedidos
from .models import Cobro
from .servicios import ServicioCobro


@login_required
@permission_required('cobro.view_cobro', raise_exception=True)
def lista_atenciones(request):
    atenciones = (Atencion.objects.abiertas().filter(cobro__isnull=True)
                  .select_related('mesa', 'cliente')
                  .annotate(pedidos_pendientes=Count(
                      'pedidos', filter=Q(pedidos__estado__in=Pedido.ESTADOS_EN_CURSO)))
                  .order_by('fecha_hora_ingreso', 'pk'))
    pagina = Paginator(atenciones, 12).get_page(request.GET.get('page'))
    return render(request, 'cobro/lista_atenciones.html', {'pagina': pagina})


def _atencion(id):
    return get_object_or_404(Atencion.objects.select_related('mesa', 'cliente'), pk=id)


def _contexto_consumo(atencion, form=None):
    contexto = {'atencion': atencion, 'consumo': None, 'error_consumo': ''}
    try:
        contexto['consumo'] = AdaptadorConsumoPedidos().consultar(atencion)
    except ConsumoInvalidoError as error:
        contexto['error_consumo'] = ' '.join(error.messages)
    consumo = contexto['consumo']
    contexto['form'] = form if form is not None else RegistrarCobroForm(
        total=consumo.total if consumo and consumo.lineas else None)
    return contexto


@login_required
@permission_required('cobro.view_cobro', raise_exception=True)
def detalle_consumo(request, id):
    atencion = _atencion(id)
    cobro = Cobro.objects.filter(atencion=atencion).first()
    if cobro:
        return redirect('cobro:detalle_cobro', id=cobro.pk)
    return render(request, 'cobro/detalle_consumo.html', _contexto_consumo(atencion))


@login_required
@permission_required(('cobro.view_cobro', 'cobro.add_cobro'), raise_exception=True)
@require_POST
def registrar_cobro(request, id):
    atencion = _atencion(id)
    # El formulario valida la entrada; el servicio calcula y valida el pago
    # contra el total real después de adquirir los bloqueos, nunca contra POST.
    form = RegistrarCobroForm(request.POST)
    if form.is_valid():
        try:
            cobro = ServicioCobro().registrar(
                atencion_id=atencion.pk, cajero=request.user,
                monto_recibido=form.cleaned_data['monto_recibido'],
                forma_pago=form.cleaned_data['forma_pago'],
            )
        except CobroDuplicadoError as error:
            messages.warning(request, ' '.join(error.messages))
            existente = get_object_or_404(Cobro, atencion=atencion)
            return redirect('cobro:detalle_cobro', id=existente.pk)
        except ValidationError as error:
            if hasattr(error, 'message_dict'):
                for campo, errores in error.message_dict.items():
                    form.add_error(campo if campo in form.fields else None, errores)
            else:
                form.add_error(None, error)
        else:
            messages.success(request, f'Cobro #{cobro.pk} registrado. La atención se cerró correctamente.')
            return redirect('cobro:detalle_cobro', id=cobro.pk)
    atencion.refresh_from_db()
    return render(request, 'cobro/detalle_consumo.html', _contexto_consumo(atencion, form))


@login_required
@permission_required('cobro.view_cobro', raise_exception=True)
def detalle_cobro(request, id):
    cobro = get_object_or_404(
        Cobro.objects.select_related('atencion__mesa', 'atencion__cliente', 'cajero')
        .prefetch_related('detalles'), pk=id)
    return render(request, 'cobro/detalle_cobro.html', {'cobro': cobro})


@login_required
@permission_required('cobro.view_cobro', raise_exception=True)
def historial(request):
    resumen = Cobro.objects.aggregate(
        total_cobrado=Sum('total', default=Decimal('0.00')),
        cobros_registrados=Count('pk'),
    )
    cobros = Cobro.objects.select_related('atencion__mesa', 'cajero')
    pagina = Paginator(cobros, 20).get_page(request.GET.get('page'))
    return render(request, 'cobro/historial.html', {'pagina': pagina, 'resumen': resumen})
