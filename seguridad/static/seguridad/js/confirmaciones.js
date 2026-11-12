(function () {
    'use strict';
    var modal = document.getElementById('confirmacion-seguridad');
    if (!modal) return;
    var contenido = document.getElementById('contenido-confirmacion-seguridad');
    var titulo = document.getElementById('titulo-confirmacion-seguridad');
    var peticionActual;
    var enviando = false;

    function cerrar() { if (!enviando) modal.close(); }
    document.addEventListener('click', async function (evento) {
        var enlace = evento.target.closest('a[data-confirmar]');
        if (!enlace || evento.button !== 0 || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
        evento.preventDefault();
        if (peticionActual) peticionActual.abort();
        var peticion = new AbortController();
        peticionActual = peticion;
        enviando = false;
        titulo.textContent = 'Confirmar acción';
        contenido.innerHTML = '<p class="p-4 mb-0 text-muted small">Cargando confirmación…</p>';
        contenido.setAttribute('aria-busy', 'true');
        if (!modal.open) modal.showModal();
        var url = new URL(enlace.href, window.location.href);
        url.searchParams.set('siguiente', window.location.pathname + window.location.search);
        try {
            var respuesta = await fetch(url, {headers: {'X-Requested-With': 'XMLHttpRequest'}, signal: peticion.signal});
            if (peticion.signal.aborted) return;
            if (respuesta.redirected) { window.location.assign(respuesta.url); return; }
            if (!respuesta.ok) throw new Error('Acción no disponible');
            var html = await respuesta.text();
            if (peticion.signal.aborted || !modal.open) return;
            var documento = new DOMParser().parseFromString(html, 'text/html');
            var confirmacion = documento.querySelector('[data-confirmacion-seguridad]');
            if (!confirmacion) throw new Error('Respuesta inesperada');
            contenido.innerHTML = confirmacion.outerHTML;
            titulo.textContent = confirmacion.dataset.titulo;
            contenido.querySelector('[data-cerrar-confirmacion]').focus();
        } catch (error) {
            if (!peticion.signal.aborted) contenido.innerHTML = '<div class="p-4"><p class="alert alert-danger" role="alert">No se pudo cargar la confirmación. Cierra el modal y vuelve a intentarlo.</p><button class="btn btn-outline-secondary" type="button" data-cerrar-confirmacion>Cerrar</button></div>';
        } finally {
            if (peticionActual === peticion) {
                contenido.setAttribute('aria-busy', 'false');
                peticionActual = null;
            }
        }
    });
    modal.addEventListener('click', function (evento) {
        if (evento.target.closest('[data-cerrar-confirmacion]')) cerrar();
    });
    modal.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape') { evento.preventDefault(); evento.stopPropagation(); cerrar(); }
    });
    modal.addEventListener('cancel', function (evento) { if (enviando) evento.preventDefault(); });
    modal.addEventListener('close', function () {
        if (peticionActual) peticionActual.abort();
        enviando = false;
    });
    modal.addEventListener('submit', function (evento) {
        if (!evento.target.matches('[data-form-confirmacion]')) return;
        if (enviando) { evento.preventDefault(); return; }
        enviando = true;
        evento.target.querySelector('button[type="submit"]').disabled = true;
        evento.target.querySelector('button[type="submit"]').textContent = 'Procesando…';
    });
})();
