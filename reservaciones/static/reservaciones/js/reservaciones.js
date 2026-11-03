/*
 * Selector de cliente y registro rápido (CU-04).
 * Busca clientes mientras se escribe y permite darlos de alta en un modal
 * sin abandonar la reservación o el ingreso en curso.
 */
document.addEventListener('DOMContentLoaded', function () {
    var selector = document.getElementById('selector-cliente');
    if (!selector) return;

    var urlBuscar     = selector.dataset.urlBuscar;
    var campoOculto   = document.getElementById('id_cliente');
    var elegido       = document.getElementById('cliente-elegido');
    var elegidoTexto  = document.getElementById('cliente-elegido-texto');
    var busqueda      = document.getElementById('cliente-busqueda');
    var inputBuscar   = document.getElementById('cliente-buscar');
    var resultados    = document.getElementById('cliente-resultados');
    var btnQuitar     = document.getElementById('cliente-quitar');

    function seleccionar(cliente) {
        campoOculto.value = cliente.id;
        elegidoTexto.textContent = cliente.nombre + ' · ' + cliente.telefono;
        elegido.classList.remove('d-none');
        busqueda.classList.add('d-none');
        resultados.innerHTML = '';
        inputBuscar.classList.remove('is-invalid');
    }

    function mensajeResultados(texto) {
        resultados.innerHTML = '';
        var item = document.createElement('div');
        item.className = 'list-group-item text-muted small';
        item.textContent = texto;
        resultados.appendChild(item);
    }

    btnQuitar.addEventListener('click', function () {
        campoOculto.value = '';
        elegido.classList.add('d-none');
        busqueda.classList.remove('d-none');
        inputBuscar.value = '';
        inputBuscar.focus();
    });

    // Evita que Enter en la búsqueda envíe el formulario principal.
    inputBuscar.addEventListener('keydown', function (e) {
        if (e.key === 'Enter') e.preventDefault();
    });

    var temporizador;
    inputBuscar.addEventListener('input', function () {
        clearTimeout(temporizador);
        var texto = inputBuscar.value.trim();
        if (texto.length < 2) { resultados.innerHTML = ''; return; }
        temporizador = setTimeout(function () {
            fetch(urlBuscar + '?q=' + encodeURIComponent(texto), { headers: { 'X-Requested-With': 'XMLHttpRequest' } })
                .then(function (r) { return r.json(); })
                .then(function (datos) {
                    if (!datos.clientes.length) {
                        mensajeResultados('No se encontraron clientes. Use «Nuevo cliente» para registrarlo.');
                        return;
                    }
                    resultados.innerHTML = '';
                    datos.clientes.forEach(function (cliente) {
                        var boton = document.createElement('button');
                        boton.type = 'button';
                        boton.className = 'list-group-item list-group-item-action';
                        boton.textContent = cliente.nombre + ' · ' + cliente.telefono;
                        boton.addEventListener('click', function () { seleccionar(cliente); });
                        resultados.appendChild(boton);
                    });
                })
                .catch(function () { mensajeResultados('No se pudo realizar la búsqueda. Intente de nuevo.'); });
        }, 250);
    });

    /* ── Modal: registrar cliente nuevo ── */
    var modalEl = document.getElementById('modalCliente');
    if (!modalEl) return;

    var formCliente   = document.getElementById('form-cliente');
    var inputNombre   = document.getElementById('cliente-nombre');
    var inputTelefono = document.getElementById('cliente-telefono');
    var errorGeneral  = document.getElementById('cliente-error-general');
    var duplicado     = document.getElementById('cliente-duplicado');
    var duplicadoDato = document.getElementById('cliente-duplicado-datos');
    var btnGuardar    = document.getElementById('cliente-guardar');
    var existente     = null;

    function limpiarErrores() {
        errorGeneral.classList.add('d-none');
        [inputNombre, inputTelefono].forEach(function (input) { input.classList.remove('is-invalid'); });
        formCliente.querySelectorAll('[data-error]').forEach(function (div) { div.textContent = ''; });
    }

    function mostrarDuplicado(mostrar) {
        duplicado.classList.toggle('d-none', !mostrar);
        btnGuardar.disabled = mostrar;
    }

    modalEl.addEventListener('show.bs.modal', function () {
        formCliente.reset();
        limpiarErrores();
        mostrarDuplicado(false);
        // Aprovecha lo escrito en la búsqueda.
        var texto = inputBuscar.value.trim();
        if (/^[\d\s\-+]+$/.test(texto)) { inputTelefono.value = texto; } else { inputNombre.value = texto; }
    });
    modalEl.addEventListener('shown.bs.modal', function () { inputNombre.focus(); });

    function cerrarModal() {
        bootstrap.Modal.getOrCreateInstance(modalEl).hide();
    }

    formCliente.addEventListener('submit', function (e) {
        e.preventDefault();
        limpiarErrores();
        btnGuardar.disabled = true;
        fetch(formCliente.action, {
            method: 'POST',
            body: new FormData(formCliente),
            headers: { 'X-Requested-With': 'XMLHttpRequest' },
        })
            .then(function (r) { return r.json().then(function (datos) { return { estado: r.status, datos: datos }; }); })
            .then(function (respuesta) {
                btnGuardar.disabled = false;
                var datos = respuesta.datos;
                if (respuesta.estado === 400 && datos.errores) {
                    Object.keys(datos.errores).forEach(function (campo) {
                        var input = formCliente.querySelector('[name="' + campo + '"]');
                        var div = formCliente.querySelector('[data-error="' + campo + '"]');
                        if (input && div) {
                            input.classList.add('is-invalid');
                            div.textContent = datos.errores[campo].join(' ');
                        } else {
                            errorGeneral.textContent = datos.errores[campo].join(' ');
                            errorGeneral.classList.remove('d-none');
                        }
                    });
                } else if (datos.existe) {
                    existente = datos.cliente;
                    duplicadoDato.textContent = datos.cliente.nombre + ' · ' + datos.cliente.telefono;
                    mostrarDuplicado(true);
                } else if (datos.creado) {
                    seleccionar(datos.cliente);
                    cerrarModal();
                } else {
                    errorGeneral.textContent = datos.error || 'No se pudo registrar el cliente.';
                    errorGeneral.classList.remove('d-none');
                }
            })
            .catch(function () {
                btnGuardar.disabled = false;
                errorGeneral.textContent = 'No se pudo registrar el cliente. Intente de nuevo.';
                errorGeneral.classList.remove('d-none');
            });
    });

    document.getElementById('cliente-usar-existente').addEventListener('click', function () {
        if (existente) seleccionar(existente);
        cerrarModal();
    });
    document.getElementById('cliente-corregir').addEventListener('click', function () {
        mostrarDuplicado(false);
        inputTelefono.focus();
    });
});
