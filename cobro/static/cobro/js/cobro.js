/* Vista previa en centavos enteros; la validación y el cálculo definitivos son del servidor. */
document.addEventListener('DOMContentLoaded', function () {
    const form = document.getElementById('form-cobro');
    if (!form) return;
    const monto = form.elements.monto_recibido;
    const medio = form.elements.forma_pago;
    const salida = document.getElementById('cambio-estimado');
    const boton = document.getElementById('confirmar-cobro');

    function centavos(valor) {
        const partes = /^(\d{1,12})(?:\.(\d{1,2}))?$/.exec(valor);
        if (!partes) return null;
        return BigInt(partes[1]) * 100n + BigInt((partes[2] || '').padEnd(2, '0'));
    }
    function dinero(valor) {
        return '$ ' + (valor / 100n).toString().replace(/\B(?=(\d{3})+(?!\d))/g, ',')
            + '.' + (valor % 100n).toString().padStart(2, '0');
    }
    const total = centavos(form.dataset.total);
    function actualizar() {
        const recibido = centavos(monto.value);
        salida.textContent = total !== null && recibido !== null && recibido >= total
            && (medio.value === 'EFECTIVO' || recibido === total) ? dinero(recibido - total) : '—';
    }
    medio.addEventListener('change', function () {
        monto.readOnly = medio.value !== 'EFECTIVO';
        if (monto.readOnly) monto.value = form.dataset.total;
        actualizar();
    });
    monto.addEventListener('input', actualizar);
    form.addEventListener('submit', function () {
        boton.disabled = true;
        boton.textContent = 'Registrando…';
    });
    window.addEventListener('pageshow', function () { boton.disabled = false; });
    actualizar();
});
