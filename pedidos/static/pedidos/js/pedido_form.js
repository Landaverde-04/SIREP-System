document.addEventListener('DOMContentLoaded', function () {
    var cuerpo     = document.getElementById('detalles-cuerpo');
    var totalForms = document.getElementById('id_detalles-TOTAL_FORMS');
    var plantilla  = document.getElementById('detalle-plantilla');
    var btnAgregar = document.getElementById('btn-agregar-detalle');

    if (!cuerpo || !totalForms || !plantilla || !btnAgregar) return;

    // Agrega una fila nueva a partir de la plantilla vacía del formset.
    btnAgregar.addEventListener('click', function () {
        var indice = parseInt(totalForms.value, 10);
        cuerpo.insertAdjacentHTML(
            'beforeend',
            plantilla.innerHTML.replace(/__prefix__/g, indice)
        );
        totalForms.value = indice + 1;
    });

    // Quitar una fila: se marca su casilla DELETE y se oculta la fila.
    cuerpo.addEventListener('click', function (e) {
        var btn = e.target.closest('.btn-quitar-detalle');
        if (!btn) return;
        var fila = btn.closest('tr');
        var borrar = fila.querySelector('input[type="checkbox"][name$="-DELETE"]');
        if (borrar) borrar.checked = true;
        fila.classList.add('d-none');
    });
});
