/* Formularios de administración: formato de teléfono, nombres y vista previa de la mesa. */
document.addEventListener('DOMContentLoaded', function () {

    // Teléfono: solo 8 dígitos y guion automático (7777-8888).
    document.querySelectorAll('[data-telefono]').forEach(function (input) {
        input.setAttribute('maxlength', '9');
        input.addEventListener('input', function () {
            var d = input.value.replace(/\D/g, '').slice(0, 8);
            input.value = d.length > 4 ? d.slice(0, 4) + '-' + d.slice(4) : d;
        });
    });

    // Nombre: mayúscula inicial al salir del campo (el servidor aplica la misma regla).
    var conectores = ['de', 'del', 'la', 'las', 'los', 'y', 'e', 'van', 'von', 'da', 'di'];
    document.querySelectorAll('[data-nombre]').forEach(function (input) {
        input.addEventListener('blur', function () {
            input.value = input.value.trim().split(/\s+/).map(function (palabra, i) {
                var m = palabra.toLowerCase();
                if (i > 0 && conectores.indexOf(m) !== -1) return m;
                return m.split('-').map(function (p) { return p.charAt(0).toUpperCase() + p.slice(1); }).join('-');
            }).join(' ');
        });
    });

    // Vista previa de la mesa mientras se escribe número y capacidad.
    var vista = document.getElementById('vista-mesa');
    if (vista) {
        var numero = document.getElementById('id_numero');
        var capacidad = document.getElementById('id_capacidad');
        var arriba = vista.querySelector('[data-lado="arriba"]');
        var abajo = vista.querySelector('[data-lado="abajo"]');
        var tablero = vista.querySelector('.mesa-tablero');
        var texto = document.getElementById('vista-mesa-texto');
        var dibujar = function () {
            var c = Math.max(0, Math.min(50, parseInt(capacidad.value, 10) || 0));
            var a = Math.min(Math.ceil(c / 2), 6), b = Math.min(Math.floor(c / 2), 6);
            arriba.innerHTML = '<span></span>'.repeat(a);
            abajo.innerHTML = '<span></span>'.repeat(b);
            var extra = c - a - b;
            tablero.innerHTML = (numero.value || '?') + (extra > 0 ? '<small>+' + extra + '</small>' : '');
            tablero.style.width = Math.max(64, Math.max(a, 1) * 24 + 16) + 'px';
            texto.textContent = c ? c + (c === 1 ? ' persona' : ' personas') : 'Indique la capacidad';
        };
        numero.addEventListener('input', dibujar);
        capacidad.addEventListener('input', dibujar);
        dibujar();
    }
});
