(function () {
    'use strict';

    const selector = document.querySelector('[data-permisos-rol]');
    const todos = selector?.querySelector('[data-permisos-todos]');
    if (!todos) return;

    const permisos = [...selector.querySelectorAll('[data-permiso]')];
    const contadorGeneral = selector.querySelector('[data-contador-general]');
    const grupos = [...selector.querySelectorAll('[data-grupo-permisos]')].map(grupo => ({
        elemento: grupo,
        boton: grupo.querySelector('[data-grupo-toggle]'),
        cuerpo: grupo.querySelector('[data-grupo-cuerpo]'),
        todos: grupo.querySelector('[data-grupo-todos]'),
        contador: grupo.querySelector('[data-grupo-contador]'),
        permisos: [...grupo.querySelectorAll('[data-permiso]')],
    }));

    function actualizarControl(casilla, contador, opciones) {
        const seleccionados = opciones.filter(opcion => opcion.checked).length;
        casilla.checked = seleccionados === opciones.length;
        casilla.indeterminate = seleccionados > 0 && seleccionados < opciones.length;
        contador.textContent = seleccionados + ' de ' + opciones.length;
    }

    function actualizarSeleccion() {
        grupos.forEach(grupo => actualizarControl(grupo.todos, grupo.contador, grupo.permisos));
        actualizarControl(todos, contadorGeneral, permisos);
    }

    function marcar(opciones, estado) {
        opciones.forEach(opcion => { opcion.checked = estado; });
    }

    grupos.forEach(grupo => {
        grupo.cuerpo.hidden = true;
        grupo.boton.setAttribute('aria-expanded', 'false');
        grupo.elemento.querySelector('[data-control-grupo]').hidden = false;
        grupo.contador.hidden = false;
        grupo.boton.addEventListener('click', () => {
            grupo.cuerpo.hidden = !grupo.cuerpo.hidden;
            grupo.boton.setAttribute('aria-expanded', String(!grupo.cuerpo.hidden));
        });
        grupo.todos.addEventListener('change', () => marcar(grupo.permisos, grupo.todos.checked));
    });

    todos.addEventListener('change', () => marcar(permisos, todos.checked));
    selector.addEventListener('change', actualizarSeleccion);
    window.addEventListener('pageshow', actualizarSeleccion);
    actualizarSeleccion();
    selector.querySelector('[data-control-general]').hidden = false;
})();
