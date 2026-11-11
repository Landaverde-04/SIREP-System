# Módulo de cobro de SIREP

## Alcance y estado

El módulo implementa CU-13, CU-14 y CU-15, HU-13, HU-14 y HU-15, y las
reglas RN-08 y RN-09 conforme al alcance autorizado. La primera fase aceptada
(`consumo.py` y sus 17 pruebas) se conserva sin modificaciones. La segunda
fase incorpora integración real con pedidos, persistencia histórica, pago
completo, cierre transaccional, permisos e interfaz responsive.
La mejora de consulta permite además revisar productos todavía no entregados
y un estimado provisional, sin modificar el importe ni las condiciones del cobro.

El componente `cobro.consumo` calcula subtotales y total sin importar Django,
consultar productos ni acceder a una base de datos. No registra pagos.
El registro del pago se realiza mediante `ServicioCobro`, no mediante el
componente matemático ni desde el administrador Django.

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
- Como consulta adicional, mostrar todos los productos solicitados no
  cancelados con sus estados y un total estimado informativo. Este resumen no
  cambia HU-13/HU-14/HU-15 ni autoriza pagos anticipados.

La solicitud de implementación especificó HU-13 (detalle entregado), HU-14
(total automático) y HU-15 (pago y liberación), incluidos el bloqueo por pedidos
en curso y la prohibición de pagos vacíos. El documento completo de Etapa 1
no está incluido en el repositorio. Las reglas monetarias siguientes son
decisiones de diseño autorizadas, no criterios atribuidos a ese documento.

## Reglas de pago implementadas

- `EFECTIVO`: monto recibido mayor o igual al total; cambio = recibido - total.
- `TARJETA` y `OTRO`: monto recibido exactamente igual al total, sin cambio.
- Cobro completo: no se admiten pagos parciales ni división de cuenta.
- Importes `Decimal` positivos, finitos, de hasta 14 dígitos (12 enteros y dos
  decimales). No se redondean entradas con precisión adicional ni se aceptan
  `float` en el servicio. El navegador envía texto que valida `DecimalField`.
- El formulario solicita confirmación del pago y del cierre. Cajero, fecha,
  total y cambio se determinan en el servidor; valores POST para esos campos
  no se utilizan.
- La vista previa de cambio usa centavos enteros (`BigInt`) en JavaScript.
  Es informativa: las reglas se vuelven a aplicar dentro de la transacción.

## Responsables y dependencias

| Módulo | Responsable | Dependencia para cobro |
|---|---|---|
| Pedidos | Daniel | Relación con la atención, detalles, cantidades, precios históricos y criterio de entregado o pendiente. |
| Reservaciones | Samuel | Modelo `Atencion`, cierre y disponibilidad según reservaciones. |
| Administración | Waldo | `Mesa`, `Cliente`, `Producto`, `CategoriaProducto` y contrato de estado de mesa. |

Se reutilizan los modelos integrados, sin cambiar sus campos. El cálculo
autorizado para cobro selecciona `Pedido.Estado.ENTREGADO`; no usa
`facturables()`, porque ese método también incluye pedidos en curso.
La consulta ampliada incluye también esos pedidos para el estimado.
`Pedido.ESTADOS_EN_CURSO` identifica
`PENDIENTE`, `EN_PREPARACION` y `LISTO`: cualquiera impide confirmar el pago.
Los cancelados se excluyen. No se filtra por `activo` para ocultar consumos.

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

## Consumo entregado y total estimado

La pantalla muestra los productos de pedidos `PENDIENTE`, `EN_PREPARACION`,
`LISTO` y `ENTREGADO` con nombre, cantidad, precio histórico, subtotal y estado.
Se excluye `CANCELADO` tanto del listado como de ambos cálculos. Las etiquetas
distinguen los productos entregados de aquellos todavía en curso; en móvil
el estado aparece debajo del nombre para conservar una tabla legible.

| Importe | Qué suma | Uso |
|---|---|---|
| Total entregado | Solo detalles de pedidos `ENTREGADO`. | Es la base del cobro, pero exige además que no haya pendientes y se cumplan las validaciones de pago. |
| Total estimado de la atención | Detalles de todos los pedidos no cancelados. | Informativo y provisional; no autoriza un pago ni se guarda en el historial. |

Ejemplo: productos entregados por $8.50 y pendientes por $6.00 muestran
entregado $8.50 y estimado $14.50, con cobro bloqueado. Si ninguno se ha
entregado, el entregado es $0.00 y se conserva el estimado completo. Cuando
todos estén resueltos, ambos totales coinciden y el pago se calcula sobre lo
entregado. Cada nueva consulta relee los pedidos y refleja las altas y
modificaciones válidas realizadas mediante el módulo de pedidos.

`AdaptadorConsumoPedidos.consultar()` devuelve `ConsultaConsumoAtencion`,
que compone el `ConsumoAtencion` entregado con `lineas_solicitadas` y un
`ConsumoCalculado` estimado. `total`, `lineas`, `pendientes` y
`puede_cobrarse` conservan su significado original; `total_estimado` es una
propiedad separada. Ambos cálculos utilizan `ServicioConsumo` y los precios
históricos de `DetallePedido.precio_unitario`, nunca el precio del catálogo.
La etiqueta de estado y el cálculo utilizan los mismos pedidos leídos para
esa consulta. Si una línea solicitada carece de precio válido, se rechaza la
consulta completa en lugar de mostrar cifras parciales.

La ruta transaccional `ServicioCobro.registrar()` sigue utilizando
`desde_datos()` con filas bloqueadas: no consulta ni utiliza el estimado.
No se modificaron `ServicioConsumo`, los modelos de cobro, sus migraciones,
el servicio de pago, sus reglas, ni las pruebas originales o de concurrencia.

Consultar nunca cierra la atención. Si hay pendientes se muestra el aviso
"Hay pedidos pendientes de entregar. Puedes consultar el consumo, pero el
cobro estará disponible cuando todos los pedidos estén resueltos". El botón
de registro permanece deshabilitado y no se presenta un formulario de pago.
Lo mismo aplica si no hay consumo entregado o existen errores. Sin permiso
de registro el usuario tiene acceso de consulta. El servidor conserva la
validación de pendientes dentro de la transacción incluso ante un POST directo.

El precio debe haberse conservado al registrar el detalle del pedido; obtener
el precio actual del catálogo al cobrar no conserva el historial. Un cambio
posterior del catálogo no altera los datos ya recibidos por este componente.
La escala de centavos sigue el precio decimal de dos posiciones del catálogo
inspeccionado. No se añaden impuestos, descuentos ni propinas.

## Persistencia, atomicidad y concurrencia

`Cobro` se relaciona de manera única y protegida con `Atencion`. Conserva
`total`, `monto_recibido`, `forma_pago`, `fecha_hora_pago` y `cajero`. El cambio
se deriva de los importes guardados. `DetalleCobro` conserva la referencia
protegida y única al detalle original, nombre del producto, cantidad y precio
histórico. Cambiar el catálogo no modifica el desglose confirmado.

`ServicioCobro.registrar()` ejecuta dentro de `transaction.atomic()`:

1. Verificar usuario activo con permiso `cobro.add_cobro`.
2. Bloquear mesa con `SELECT FOR NO KEY UPDATE`, atención con `FOR UPDATE`,
   pedidos por PK y detalles por PK. Los bloqueos de pedidos y detalles usan
   `of=('self',)` para no bloquear las relaciones precargadas.
3. Rechazar atención cerrada, cobro existente y pedidos en curso después de
   adquirir los bloqueos. Recalcular el consumo y validar el pago.
4. Guardar cobro y todos sus detalles; invocar `Atencion.cerrar()`.

La restricción `OneToOneField` impide duplicados en PostgreSQL, y las
restricciones CHECK rechazan total no positivo y pagos incoherentes. Cualquier
fallo revierte cobro, detalles y cierre.

El orden respeta mesa -> atención -> pedido -> detalle. Pedidos.guardar()
bloquea atención antes de pedido; cambiar_estado() bloquea el pedido. La mesa
usa `NO KEY UPDATE` para permitir la comprobación de su FK al confirmar un
pedido que ya retenía atención: usar `FOR UPDATE` en mesa produciría un
posible ciclo mesa -> atención -> FK de mesa. Las pruebas de concurrencia
ejercitan estas carreras mediante conexiones independientes y verifican
esperas con `pg_blocking_pids`, sin reemplazar los servicios por simulaciones.

En el modelo integrado, `Mesa.estado` es una propiedad calculada. Cobro no
escribe ese estado ni habilita mesas: cerrar la atención quita su ocupación,
y `ServicioDisponibilidad` conserva las restricciones de reservaciones.

## Protección y límites reales del historial

Cobros y detalles heredan los campos de `ModeloBase`, pero son inmutables:
`save()` de un registro persistido, `delete()`, `QuerySet.update/delete`,
`bulk_update` y los upserts mediante `bulk_create` rechazan cambios. Sus
referencias usan PROTECT y el administrador de cobro permite solo consulta.
No se permiten nuevas líneas para una atención ya cerrada.

Esto protege las interfaces y operaciones ORM habituales; no constituye un
registro inviolable frente a SQL directo ni frente a escrituras deliberadas
que omitan los servicios. El administrador de pedidos existente permite
operaciones ajenas a `ServicioPedidos`; no se alteró porque está fuera del
alcance autorizado. Para extender las garantías a esas escrituras se requiere
coordinar su protección con Daniel y Kevin.

## Estructura e interfaz Django

La aplicación contiene sus modelos, vistas, formularios, servicios, rutas,
plantillas y estáticos. `base_cobro.html` hereda de `core/base.html` y aporta
solo recursos y estructura específica del módulo.

- Las rutas específicas están en `cobro/urls.py`, con espacio de nombres
  `cobro`. `sirep/urls.py` solamente las incluye.
- Las plantillas heredan `core/base.html`. La ubicación real de la base es
  `core/templates/core/base.html`; sus bloques son `titulo`, `estilos_extra`,
  `contenido` y `scripts_extra`.
- La base ya carga Bootstrap 5.3.3, Bootstrap Icons, los estilos y JavaScript
  compartidos, los mensajes y el menú mediante `core/sidebar.html`. Las
  pantallas de cobro reutilizan esa estructura sin duplicar HTML ni menú.
- El contenido se coloca en `contenido`; los recursos específicos de
  `static/cobro/` se cargan mediante `estilos_extra` y `scripts_extra`.
- Se aplican autenticación, permisos de Django, CSRF y las convenciones de
  vistas del proyecto. Las validaciones de cobro se aplicarán en el servidor.

En la implementación inicial, los únicos archivos externos modificados fueron
`sirep/urls.py` y `core/templates/core/sidebar.html`, autorizados para rutas y
enlace con permiso. Esta mejora de consulta modifica exclusivamente `cobro/`:
conserva intactos el sidebar, la base, las rutas generales y los demás módulos.
`seguridad/forms.py` ya contempla `cobro` y se conserva intacto.

## Inicio y uso desde el navegador

Desde la raíz, con el entorno virtual activo y PostgreSQL disponible:

```text
python manage.py migrate cobro --plan
python manage.py migrate cobro
python manage.py runserver
```

1. Iniciar sesión y asignar al rol del cajero `cobro.view_cobro` y
   `cobro.add_cobro` mediante la gestión de roles existente. Un usuario con
   solo `view_cobro` puede consultar; para registrar desde la web se exigen ambos.
2. Abrir `http://127.0.0.1:8000/cobro/` o el enlace Cobros del sidebar.
3. Seleccionar una atención. Si no existe, registrar el ingreso mediante
   reservaciones. Los pedidos se toman y entregan mediante el módulo de pedidos.
4. Consultar productos solicitados, estados y precios históricos. Distinguir
   el total entregado del estimado provisional; resolver los pendientes antes
   de pagar y actualizar la consulta para ver los cambios.
5. Elegir medio, ingresar monto y confirmar. El botón registra el pago y cierra
   la atención en una operación. La pantalla siguiente muestra total,
   recibido, cambio, cajero, fecha y desglose histórico.
6. Consultar pagos anteriores en `http://127.0.0.1:8000/cobro/historial/`.

El usuario de solo consulta no ve el formulario de pago. El historial no
ofrece edición, eliminación ni documentos tributarios.

## Verificación

Desde la raíz del repositorio, con el entorno virtual activo:

```text
python -B -m unittest cobro.tests -v
python -B manage.py test cobro --verbosity 2
python -B manage.py test administracion reservaciones pedidos seguridad cobro
python -B manage.py check
python -B manage.py makemigrations --check --dry-run
python -B manage.py migrate --check
```

Resultado verificado el 9 de noviembre de 2026:

| Comprobación | Resultado |
|---|---|
| Suite final de cobro | 87 aprobadas: 17 originales, 54 de segunda fase (incluidas tres de concurrencia) y 16 de consulta estimada. |
| Regresión conjunta de los cinco módulos | 218 aprobadas; incluye las 131 de los otros módulos. Sin fallos ni omisiones. |
| `manage.py check` | Sin problemas. |
| `makemigrations --check --dry-run` | Sin cambios pendientes de generar. |
| Migración inicial, aplicada en la fase anterior | `0001_initial` continúa aplicada. Esta mejora no añade ni modifica migraciones. |
| `migrate --check` | Sin migraciones pendientes. |
| `node --check` del JavaScript de cobro | Sin errores de sintaxis. |
| Chrome headless, escritorio y móvil | Consultas pendientes, mixtas y entregadas a 1440 y 390 px sin desbordamiento horizontal; ambos totales, estados, bloqueo y vista previa de cambio comprobados. |

Las capturas visuales usan HTML generado por las vistas con datos reales de
los modelos en la instancia temporal. El flujo HTTP de pedido, preparación,
entrega y cobro se verifica además con el cliente de Django, CSRF activo y
servicios reales. Se verificó por SHA-256 que `consumo.py` y `tests.py` no
cambiaron respecto de la primera fase aceptada.

Las 17 pruebas originales siguen siendo independientes de Django y de la base.
Las nuevas pruebas de integración usan los modelos, vistas y servicios reales
en una base temporal. Las tres pruebas de concurrencia requieren PostgreSQL;
en otros motores se omiten explícitamente y no verifican bloqueos.
`tests_consulta.py` añade 16 casos sobre ambos totales, los tres estados en
curso, cancelados, precios históricos, edición real de pedidos mediante sus
formularios y servicio, botón bloqueado, rechazo de POST anticipado, pago
posterior a entrega, duplicados y conservación del historial confirmado.

El servidor local rechazó la creación automática de la base de pruebas por
falta de CREATEDB. No se modificaron privilegios. La verificación de integración
se realizó con PostgreSQL 18.6 en una instancia temporal separada, usando los
binarios locales; se cambió la configuración únicamente en el proceso de
prueba, sin editar `.env` ni usar datos del servidor habitual. Un administrador
debe proporcionar una base de pruebas adecuada o CREATEDB si se desea repetir
la ejecución con el usuario local. No ejecutar las pruebas contra la base de
negocio como sustituto de una base temporal.

## Inventario de archivos de esta fase

Modificados: `README.md`, `models.py`, `views.py`, `admin.py` dentro de
`cobro/`, más `sirep/urls.py` y `core/templates/core/sidebar.html`.

Creados dentro de `cobro/`:

- `excepciones.py`, `pagos.py`, `forms.py`, `integracion.py`, `servicios.py`, `urls.py`.
- `migrations/0001_initial.py`.
- `tests_integracion.py`, `tests_concurrencia.py`.
- `static/cobro/css/cobro.css`, `static/cobro/js/cobro.js`.
- `templates/cobro/base_cobro.html`, `lista_atenciones.html`,
  `detalle_consumo.html`, `detalle_cobro.html`, `historial.html` y
  `parciales/paginacion.html`, todos bajo el mismo directorio de plantillas.

### Mejora de consulta estimada

Modificados exclusivamente dentro de `cobro/`:

- `integracion.py`: composición de la consulta provisional, conservando el
  cálculo entregado y la ruta transaccional.
- `templates/cobro/base_cobro.html`, `lista_atenciones.html`,
  `detalle_consumo.html` y `detalle_cobro.html`: encabezados sin decoración,
  productos y estados, dos totales identificados y bloqueo visible del botón.
- `static/cobro/css/cobro.css`: distinción visual de filas en curso con los
  colores compartidos.
- `README.md`: alcance, diferencia de importes y resultados reales.

Archivos nuevos: `tests_consulta.py` y
`templates/cobro/parciales/estado_pedido.html`. El historial conserva su
funcionamiento; los importes estimados no se almacenan ni modifican cobros
anteriores. No se modificaron modelos, servicios o migraciones de otros módulos.

## Documentación posterior

- UML de componentes: representar vistas/formularios -> ServicioCobro ->
  adaptador -> ServicioConsumo, repositorios Cobro/DetalleCobro, dependencias
  a Pedidos, Atencion, Mesa, Usuario y PostgreSQL; señalar la frontera atómica.
- Pruebas documentadas: asociar HU-13/HU-14/HU-15 con los casos de
  `tests_integracion.py` y `tests_concurrencia.py`, registrar motor y versión,
  comandos, resultados y evidencia de reversión y concurrencia.
- Manual de usuario: permisos del cajero, selección de atención, resolución
  de pendientes, diferencia entre entregado y estimado, pago en efectivo/no
  efectivo, confirmación e historial.
  Incorporar capturas y mensajes reales antes de publicar el manual.
