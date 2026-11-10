(function () {
    'use strict';

    var formulario = document.getElementById('filtros-usuarios');
    var resultados = document.getElementById('resultados-usuarios');
    var error = document.getElementById('error-busqueda');
    if (!formulario || !resultados) return;

    var buscador = document.getElementById('buscador');
    var temporizador;
    var peticionActual;

    function consultaAplicada() {
        var seccion = resultados.querySelector('[data-consulta-aplicada]');
        return seccion ? seccion.dataset.consultaAplicada : '';
    }

    function direccionFormulario() {
        var url = new URL(formulario.action, window.location.href);
        url.search = new URLSearchParams(new FormData(formulario)).toString();
        return url;
    }

    function sincronizarFormulario(url) {
        var parametros = url.searchParams;
        buscador.value = parametros.get('q') || '';
        formulario.elements.ordenar.value = parametros.get('ordenar') || 'usuario';
        formulario.elements.direccion.value = parametros.get('direccion') || 'asc';
        var valores = parametros.getAll('estado');
        var estado = valores.length ? valores[valores.length - 1] : 'activo';
        if (!['activo', 'inactivo'].includes(estado)) estado = 'activo';
        formulario.querySelectorAll('input[name="estado"]').forEach(function (campo) {
            campo.checked = campo.value === estado;
        });
    }

    function cancelarBusqueda() {
        window.clearTimeout(temporizador);
        if (peticionActual) peticionActual.abort();
    }

    async function cargar(url, historial) {
        cancelarBusqueda();
        var peticion = new AbortController();
        peticionActual = peticion;
        resultados.setAttribute('aria-busy', 'true');
        error.classList.add('d-none');
        try {
            var respuesta = await fetch(url, {
                headers: {'X-Requested-With': 'XMLHttpRequest'},
                signal: peticion.signal
            });
            if (peticion.signal.aborted) return;
            if (respuesta.redirected) {
                window.location.assign(respuesta.url);
                return;
            }
            if (!respuesta.ok) throw new Error('No se pudo consultar el listado');
            var html = await respuesta.text();
            if (peticion.signal.aborted) return;
            resultados.innerHTML = html;
            sincronizarFormulario(url);
            if (historial === 'push') window.history.pushState({}, '', url);
            if (historial === 'replace') window.history.replaceState({}, '', url);
        } catch (excepcion) {
            if (!peticion.signal.aborted) error.classList.remove('d-none');
        } finally {
            if (peticionActual === peticion) {
                resultados.setAttribute('aria-busy', 'false');
                peticionActual = null;
            }
        }
    }

    buscador.addEventListener('input', function () {
        cancelarBusqueda();
        // Con una letra no se inicia una búsqueda. Si había una consulta aplicada,
        // se recupera el listado sin búsqueda para no dejar resultados anteriores.
        if (buscador.value.trim().length === 1 && !consultaAplicada()) {
            resultados.setAttribute('aria-busy', 'false');
            return;
        }
        temporizador = window.setTimeout(function () {
            cargar(direccionFormulario(), 'replace');
        }, 300);
    });

    formulario.addEventListener('submit', function (evento) {
        evento.preventDefault();
        cargar(direccionFormulario(), 'push');
    });

    formulario.querySelectorAll('input[name="estado"]').forEach(function (campo) {
        campo.addEventListener('change', function () {
            cargar(direccionFormulario(), 'push');
        });
    });

    resultados.addEventListener('click', function (evento) {
        var enlace = evento.target.closest('a[data-listado]');
        if (!enlace || evento.button !== 0 || evento.ctrlKey || evento.metaKey || evento.shiftKey || evento.altKey) return;
        evento.preventDefault();
        cargar(new URL(enlace.href, window.location.href), 'push');
    });

    window.addEventListener('popstate', function () {
        var url = new URL(window.location.href);
        sincronizarFormulario(url);
        cargar(url, null);
    });
})();
