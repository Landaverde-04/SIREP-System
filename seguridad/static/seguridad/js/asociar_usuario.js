(function () {
    'use strict';
    var modal = document.getElementById('modal-asociar-usuario');
    var abrir = document.getElementById('abrir-asociacion');
    if (!modal || !abrir) return;
    var formulario = document.getElementById('buscar-usuario-disponible');
    var buscador = document.getElementById('busqueda-usuario-disponible');
    var resultados = document.getElementById('resultados-usuarios-disponibles');
    var confirmar = document.getElementById('confirmar-asociacion');
    var seleccionado = document.getElementById('usuario-seleccionado');
    var temporizador;
    var peticionActual;
    var enviando = false;

    function cancelarBusqueda() {
        window.clearTimeout(temporizador);
        if (peticionActual) peticionActual.abort();
    }
    function limpiarSeleccion() {
        confirmar.disabled = true;
        seleccionado.textContent = 'Selecciona un usuario para continuar.';
        resultados.querySelectorAll('input[name="usuario"]').forEach(function (campo) { campo.checked = false; });
    }
    function direccionBusqueda() {
        var url = new URL(modal.dataset.listaUrl, window.location.href);
        url.search = new URLSearchParams(new FormData(formulario)).toString();
        return url;
    }
    async function cargar(url) {
        cancelarBusqueda();
        limpiarSeleccion();
        var peticion = new AbortController();
        peticionActual = peticion;
        resultados.setAttribute('aria-busy', 'true');
        resultados.innerHTML = '<p class="text-muted text-center py-4 mb-0">Buscando usuarios…</p>';
        try {
            var respuesta = await fetch(url, {signal: peticion.signal});
            if (peticion.signal.aborted) return;
            if (respuesta.redirected) { window.location.assign(respuesta.url); return; }
            if (!respuesta.ok && respuesta.status !== 409) throw new Error('No se pudo consultar');
            var html = await respuesta.text();
            if (!peticion.signal.aborted && modal.open) resultados.innerHTML = html;
        } catch (error) {
            if (!peticion.signal.aborted) {
                resultados.innerHTML = '<p class="alert alert-danger mb-0" role="alert">No se pudo cargar la lista. Inténtalo de nuevo con el botón Buscar.</p>';
            }
        } finally {
            if (peticionActual === peticion) {
                resultados.setAttribute('aria-busy', 'false');
                peticionActual = null;
            }
        }
    }
    abrir.addEventListener('click', function () {
        modal.showModal();
        buscador.focus();
        cargar(direccionBusqueda());
    });
    modal.querySelectorAll('[data-cerrar-asociacion]').forEach(function (boton) {
        boton.addEventListener('click', function () { modal.close(); });
    });
    modal.addEventListener('keydown', function (evento) {
        if (evento.key === 'Escape') {
            evento.preventDefault();
            evento.stopPropagation();
            modal.close();
        }
    });
    modal.addEventListener('close', function () {
        cancelarBusqueda();
        limpiarSeleccion();
    });
    buscador.addEventListener('input', function () {
        cancelarBusqueda();
        limpiarSeleccion();
        var seccion = resultados.querySelector('[data-consulta-aplicada]');
        if (buscador.value.trim().length === 1 && seccion && !seccion.dataset.consultaAplicada) {
            resultados.setAttribute('aria-busy', 'false');
            return;
        }
        temporizador = window.setTimeout(function () { cargar(direccionBusqueda()); }, 300);
    });
    formulario.addEventListener('submit', function (evento) {
        evento.preventDefault();
        cargar(direccionBusqueda());
    });
    resultados.addEventListener('click', function (evento) {
        var enlace = evento.target.closest('a[data-pagina-usuario]');
        if (!enlace || evento.button !== 0 || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
        evento.preventDefault();
        cargar(new URL(enlace.getAttribute('href'), new URL(modal.dataset.listaUrl, window.location.href)));
    });
    resultados.addEventListener('change', function (evento) {
        if (evento.target.matches('input[name="usuario"]')) {
            confirmar.disabled = false;
            seleccionado.textContent = 'Usuario seleccionado: ' + evento.target.dataset.nombre;
        }
    });
    document.getElementById('form-asociar-usuario').addEventListener('submit', function (evento) {
        if (enviando || !resultados.querySelector('input[name="usuario"]:checked')) {
            evento.preventDefault();
            return;
        }
        enviando = true;
        confirmar.disabled = true;
    });
})();
