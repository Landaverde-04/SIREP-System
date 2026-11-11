(function () {
    'use strict';
    var boton = document.getElementById('ver-password');
    if (!boton) return;
    var campo = document.getElementById(boton.getAttribute('aria-controls'));
    boton.addEventListener('click', function () {
        var mostrar = campo.type === 'password';
        campo.type = mostrar ? 'text' : 'password';
        boton.setAttribute('aria-pressed', String(mostrar));
        boton.setAttribute('aria-label', mostrar ? 'Ocultar contraseña' : 'Mostrar contraseña');
        boton.querySelector('i').className = mostrar ? 'bi bi-eye-slash' : 'bi bi-eye';
    });
})();
