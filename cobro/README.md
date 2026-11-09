# Módulo de cobro de SIREP

## Alcance y estado

El módulo corresponde a CU-13, CU-14 y CU-15, HU-13, HU-14 y HU-15, y las
reglas RN-08 y RN-09. La primera fase fue revisada y aceptada: implementa
exclusivamente el cálculo independiente del consumo y cuenta con 17 pruebas
aprobadas, tanto con `unittest` como con el ejecutor de Django. La verificación
`manage.py check` de esa fase terminó sin problemas.

El componente `cobro.consumo` calcula subtotales y total sin importar Django,
consultar productos ni acceder a una base de datos. No registra pagos.
El código y las pruebas aceptados se conservan sin cambios en esta actualización
de documentación. La segunda fase todavía no está implementada.

## Requisitos del módulo completo

Según las indicaciones de Kevin y los requisitos de la documentación de SIREP
comunicados por el responsable del módulo:

- Calcular exclusivamente el consumo entregado de una atención, usando la
  cantidad y el precio unitario histórico de cada detalle.
- Impedir el cobro mientras existan pedidos pendientes de esa atención.
- Registrar el monto recibido, la forma de pago, la fecha y el cajero.
- Evitar cobros duplicados.
- Registrar el pago, cerrar la atención y liberar correctamente la mesa de
  manera atómica, respetando las reservaciones y la deshabilitación de mesas.
- No emitir documentos tributarios ni procesar pagos electrónicos. Registrar
  una forma de pago no implica integrar una pasarela ni ejecutar un cargo.

Los requisitos completos HU-13, HU-14 y HU-15 se encuentran en el documento de
la Etapa 1. Su texto completo aún debe cotejarse antes de concretar los criterios
de aceptación restantes, los valores permitidos de forma de pago y las reglas
de validación del monto recibido. Las reglas anteriores ya son requisitos
confirmados; no dependen de decisiones futuras de diseño.

## Responsables y dependencias

| Módulo | Responsable | Dependencia para cobro |
|---|---|---|
| Pedidos | Daniel | Relación con la atención, detalles, cantidades, precios históricos y criterio de entregado o pendiente. |
| Reservaciones | Samuel | Modelo `Atencion`, cierre y disponibilidad según reservaciones. |
| Administración | Waldo | `Mesa`, `Cliente`, `Producto`, `CategoriaProducto` y contrato de estado de mesa. |

El cobro debe reutilizar los modelos definitivos de estos módulos. No se
duplicarán modelos ni se inventarán campos o estados para suplir contratos
todavía no integrados.

## Contrato de entrada

`ServicioConsumo.calcular()` recibe un iterable de `DetalleConsumo`:

- `cantidad`: entero positivo; no acepta booleanos ni cantidades fraccionarias.
- `precio_unitario`: `Decimal` histórico, finito y positivo, expresable en
  centavos. Acepta `Decimal('1.5000')` como `Decimal('1.50')`; rechaza
  `Decimal('1.001')` sin redondearlo. No convierte `float`, texto ni enteros.

Los datos inválidos de un detalle producen `ValueError`. Un elemento que no
sea `DetalleConsumo` produce `TypeError` al calcular.

El resultado `ConsumoCalculado` contiene una tupla de detalles inmutables y un
total `Decimal` con dos posiciones decimales. Cada detalle expone su `subtotal`.
Un consumo vacío devuelve `Decimal('0.00')`: esto no autoriza un pago vacío.
La precisión de las operaciones se dimensiona localmente sin cambiar el
contexto decimal del llamador.

```python
from decimal import Decimal

from cobro.consumo import DetalleConsumo, ServicioConsumo

resultado = ServicioConsumo().calcular([
    DetalleConsumo(cantidad=2, precio_unitario=Decimal('3.50')),
    DetalleConsumo(cantidad=1, precio_unitario=Decimal('1.25')),
])
# Subtotales: Decimal('7.00'), Decimal('1.25'). Total: Decimal('8.25').
```

## Límites del cálculo y futura integración

La capa de integración deberá seleccionar exclusivamente los detalles
entregados de una misma atención, conforme al contrato definitivo de pedidos,
y convertirlos a `DetalleConsumo`. Este componente no presupone nombres de
campos, estados, identificadores ni modelos ORM de pedidos.
Además de seleccionar lo entregado, la futura capa transaccional deberá
comprobar que no existan pedidos pendientes antes de permitir el pago. El
cálculo de un total por sí solo no determina si la atención puede cobrarse.

El precio debe haberse conservado al registrar el detalle del pedido; obtener
el precio actual del catálogo al cobrar no conserva el historial. Un cambio
posterior del catálogo no altera los datos ya recibidos por este componente.
La escala de centavos sigue el precio decimal de dos posiciones del catálogo
inspeccionado. No se añaden impuestos, descuentos ni propinas.

Quedan pendientes los modelos y migraciones compatibles de administración y
reservaciones, el contrato de pedidos con Daniel, el cotejo del documento de
la Etapa 1 y el flujo transaccional completo. Debe resolverse la diferencia
identificada entre el estado de mesa calculado por Samuel y el estado
persistido de Waldo para que el cierre no deje la disponibilidad desactualizada.
Las operaciones concurrentes de pedidos y cobro deberán coordinarse para que
la validación de pendientes y el total sigan siendo válidos al confirmar el pago.

## Estructura e interfaz Django

Cada módulo Django tendrá sus propios modelos, vistas, plantillas, archivos
estáticos y `urls.py`. En `cobro/` ya existen `models.py`, `views.py`,
`templates/cobro/` y `static/cobro/`, inicialmente con estructura de ejemplo.
La primera fase añadió `consumo.py` y las pruebas; aún no existen rutas de
cobro ni modelos ORM de negocio implementados en este módulo.

- Las rutas específicas se definirán en `cobro/urls.py`, con espacio de nombres
  `cobro`. `sirep/urls.py` solamente incluirá esas rutas.
- Las plantillas extenderán `core/base.html`. La ubicación real de la base es
  `core/templates/core/base.html`; sus bloques son `titulo`, `estilos_extra`,
  `contenido` y `scripts_extra`.
- La base ya carga Bootstrap 5.3.3, Bootstrap Icons, los estilos y JavaScript
  compartidos, los mensajes y el menú mediante `core/sidebar.html`. Las
  pantallas de cobro reutilizarán esa estructura sin duplicar HTML ni menú.
- El contenido se colocará en `contenido`; los recursos específicos de
  `static/cobro/` se cargarán mediante `estilos_extra` y `scripts_extra`.
- Se respetarán autenticación, permisos de Django, CSRF y las convenciones de
  vistas del proyecto. Las validaciones de cobro se aplicarán en el servidor.

Los cambios necesarios en archivos compartidos, como la inclusión de rutas,
el enlace del menú y la habilitación de permisos de cobro en la gestión de
roles, requieren autorización antes de realizarlos. Actualmente
`seguridad/forms.py` filtra los permisos por `seguridad` e `inventario`, por lo
que no ofrece los de cobro en esa pantalla.

## Segunda fase propuesta, todavía sin implementar

1. Cotejar HU-13 a HU-15 y acordar con Daniel, Samuel y Waldo los contratos y
   migraciones compatibles, incluido el tratamiento de pedidos pendientes y
   la actualización del estado de mesa.
2. Diseñar los modelos propios de cobro y sus relaciones definitivas, con
   monto recibido, forma de pago, fecha, cajero, historial y unicidad por atención.
3. Conectar los detalles entregados con `ServicioConsumo` mediante un adaptador,
   conservando la lógica de cálculo aceptada. Implementar después la operación
   atómica con validación de pendientes y protección frente a concurrencia.
4. Añadir formularios, vistas, rutas y plantillas de cobro con herencia de la
   base y permisos; integrar archivos compartidos solo con autorización.
5. Probar permisos, pendientes, pago, duplicados, reversión ante fallos y
   liberación de mesa sobre PostgreSQL. Actualizar el UML de componentes para
   reflejar las interfaces y dependencias implementadas.

## Verificación

Desde la raíz del repositorio, con el entorno virtual activo:

```text
python -B -m unittest cobro.tests -v
python -B manage.py test cobro --verbosity 2
python -B manage.py check
```

Las pruebas heredan de `unittest.TestCase`: no crean bases de datos de prueba
ni consultan bases existentes. También se descubren con el ejecutor de Django.
