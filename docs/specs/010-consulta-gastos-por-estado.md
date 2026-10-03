# SPEC-010 — Consulta de gastos por estado

- Fecha: 03/10/2026. Preparación de I2; I2-T01 implementada y probada.
- Responsable: Franco, módulo gastos/pagos. Revisión independiente de coordinación
  aprobada el 03/10/2026, sin bloqueos materiales. Revisión del compañero pendiente.
- Tarea local: I2-T01. Commit local autorizado por coordinación tras su revisión;
  versión y SHA en Git y handoff local. Sin Issue nueva ni publicación autorizada.
- Fuentes: Plan de Trabajo de Franco, RF-007 y F-E09 (búsqueda, filtros y
  resúmenes de gastos); SPEC-001 para estados actuales y contrato
  `docs/contracts/identidad-demo-i1.md` para visibilidad. El handoff local conserva
  la ubicación de la fuente académica; no es una dependencia de ejecución.

## Resultado y límites

Permitir al solicitante y a las cuentas con consulta global localizar los gastos
visibles que están en un estado elegido, conservando acceso al detalle e historial.
Es una primera entrega pequeña de consultas operativas. No completa RF-007 ni
F-E09: otros filtros y resúmenes quedan para tareas posteriores. La búsqueda
textual se delimita como extensión I2-T02 al final de este documento.

La selección por estado es una concreción técnica del requisito de filtros,
no una solicitud literal de la operadora ni una prioridad institucional confirmada.
Se elige porque reutiliza información y permisos existentes y no depende de
definir pagos externos, revisión documental o nuevas transiciones.

I1 permanece pendiente de recorrido manual de Franco, reproducción de Matías,
acta acordada y devolución de Cooperadora (#8/T06 y #9/T07). Esta tarea puede
implementarse y probarse antes de esas actividades; no las sustituye ni las cierra.
H1–H4 conservan su condición provisional. Si T07 cambia los estados o la
visibilidad, se revisarán los filtros y sus pruebas junto con ese cambio.

## Contrato de consulta

- Se conserva `GET /gastos/`, el contrato de identidad y `visible_expenses(actor)`.
- Parámetro opcional `estado`, con los códigos de `EstadoSolicitud`: `presentada`,
  `postergada`, `aceptada`, `rechazada`. Las etiquetas se toman de ese mismo modelo.
- Ausencia del parámetro o valor vacío: todos los gastos visibles, con el orden
  existente (fecha descendente y luego identificador descendente).
- Valor válido: intersección entre visibilidad del actor y estado elegido.
  Se conserva la selección en el formulario y al recargar la URL.
- Valor inválido: HTTP 200 con error visible junto al selector y cero resultados;
  no se interpreta como consulta sin filtro. El enlace «Quitar filtro» recupera
  la lista sin parámetros. Si se repite `estado`, rige el último valor, conforme
  al formulario Django; cada valor efectivo pasa por la misma validación.
- Otros parámetros no alteran identidad, visibilidad ni la consulta de estados.
- Sin coincidencias: mensaje específico para el filtro; sin solicitudes y sin
  filtro se conserva el mensaje actual. Un filtro inválido muestra el error,
  sin afirmar que se ejecutó una consulta válida sin coincidencias.
- No se escriben solicitudes, decisiones ni versiones. Las condiciones sin
  actor o con demo deshabilitada siguen siendo las del contrato vigente.
- No se agregan capacidades, API, modelos, migraciones, índices, documentos,
  pagos, totales contables, catálogos de centros ni componentes de Matías.

## Primera tarea independiente: I2-T01

1. Agregar formulario de consulta con elección opcional de estado.
2. En la vista del listado, validar los parámetros y filtrar exclusivamente el
   queryset que ya devuelve `visible_expenses(actor)`.
3. Mostrar selector, botón «Filtrar», enlace «Quitar filtro», errores y mensaje
   de ausencia de coincidencias en la plantilla actual.
4. Probar con datos sintéticos, inspeccionar diff y consolidar mediante commit local
   después de la revisión independiente aprobada; no publicar sin autorización.

Archivos previstos: `gastos/forms.py`, `gastos/views.py`,
`templates/gastos/solicitud_list.html`, `tests/gastos/test_filtros_estado.py`
y esta especificación. `gastos/queries.py`, modelos, servicios de decisiones e
identidad no necesitan modificaciones.

## Aceptación y pruebas

| ID | Escenario | Resultado verificable |
|---|---|---|
| CE-01 | A filtra cada estado con gastos propios y de B en ese estado | Sólo resultados propios coincidentes; URL de detalle ajena continúa denegada. |
| CE-02 | O y L filtran cada estado | Ambas ven todos los coincidentes; L no adquiere capacidad de decidir. |
| CE-03 | Se omite estado, se envía vacío o se quita el filtro | Listado visible completo, en el orden previo. |
| CE-04 | Estado válido sin coincidencias | Lista vacía y mensaje de ausencia de coincidencias. |
| CE-05 | Estado desconocido o repetido | Error y cero resultados si el último valor es inválido; filtro validado si es válido. |
| CE-06 | Consulta sin actor, sin capacidades o con demo deshabilitada | Se mantienen redirección/denegación/lista vacía del contrato. |
| CE-07 | Consulta filtrada y recarga | Selección y enlaces correctos; solicitudes, historial y versiones inalterados. |
| CE-08 | Abrir y usar formulario del listado | Selector etiquetado, envío GET, filtro persistente y enlace funcional para quitarlo. |

Pruebas de vista con el adaptador real y PostgreSQL, incluyendo estados mezclados,
propiedad y consulta global. Reutilizar pruebas existentes de integración,
decisiones e H4 para comprobar regresiones pertinentes. Ejecutar Ruff y chequeo
Django; no repetir suites completas sin un cambio o fallo que lo justifique.
La comprobación automatizada del HTML no acredita usabilidad ni aceptación humana.

## Secuencia posterior y decisiones materiales

Antes de ampliar el circuito hacia transferencia/pago externo, precisar con la
operadora/Marcos: datos de cada etapa; relación de unidad y centro de costo;
autoridad para registrar/verificar el pago; pagos parciales o múltiples;
respaldo inicial frente a factura definitiva; correcciones y cierre. Acordar con
Matías el contrato de documentos antes de consumirlo. No fijar esas relaciones,
capacidades ni obligaciones a partir del formulario actual o de H1–H4.

Alternativas concretas tras esta tarea:

- Continuar consultas de sólo lectura con filtros adicionales/resúmenes cuando
  se delimiten sus criterios. Un importe estimado nunca se etiqueta como pagado.
- Priorizar ajustes de I1 si T07 identifica contradicciones del recorrido.
- Preparar el registro de pagos externos cuando estén resueltas las decisiones
  anteriores y exista contrato documental acordado; no ejecutar transferencias.

El primer camino permite avance técnico independiente; los otros dependen de
evidencia externa. La coordinación concilia prioridad y publicación del trabajo.

## Extensión I2-T02 — búsqueda por concepto

Contrato definido el 03/10/2026 antes de editar código, con autorización de
coordinación para implementación delimitada. Se apoya en la búsqueda de RF-007
y la consulta de F-E09. Código implementado y pruebas focalizadas aprobadas;
revisión independiente de la extensión pendiente. Franco autorizó el 03/10/2026
consolidar y avanzar con la actualización del repositorio. Se entrega para revisión
en PR borrador; esta publicación no equivale a aprobación de la extensión.

- Se conserva `GET /gastos/`; se agrega el parámetro opcional `q` al mismo formulario.
- Ausente, vacío o sólo espacios: sin búsqueda. Para buscar se quitan espacios
  exteriores; se conserva el texto enviado en el campo al renderizar y recargar.
- Término de hasta 255 caracteres, longitud del campo `SolicitudGasto.concepto`.
  El límite se aplica al término sin espacios exteriores. Un término mayor se
  rechaza en el formulario, con HTTP 200, error visible y cero resultados.
- Coincidencia por contenido de concepto mediante `concepto__icontains`, sin
  distinguir mayúsculas, usando la consulta de Django/PostgreSQL existente.
  No se agrega normalización de acentos, búsqueda aproximada ni sintaxis especial.
  `%` y `_` se buscan como caracteres literales, conforme al ORM.
- Se aplica sobre `visible_expenses(actor)` y se combina con estado mediante
  intersección: cada resultado debe satisfacer visibilidad, estado y concepto.
- Un campo inválido impide toda la consulta filtrada; no se descarta silenciosamente.
  Si se repite `q`, se valida y utiliza su último valor, como los formularios Django.
- Selector y texto se mantienen en el formulario GET; «Quitar filtro» elimina
  ambos parámetros. Una búsqueda válida sin coincidencias muestra un mensaje
  específico sin revelar solicitudes ajenas. Los casos sólo de estado conservan
  su comportamiento y mensaje previos.
- No hay escrituras en solicitudes, decisiones o versiones; tampoco cambios de
  identidad, permisos, modelos, dependencias ni contratos compartidos.

Plan: extender formulario, filtro de la vista y plantilla existentes; agregar
`tests/gastos/test_busqueda_concepto.py`. Verificar coincidencia parcial y casing,
texto vacío/espacios, combinación con estados, sólo solicitudes visibles, consulta
global y sin capacidades, límites, literales, conservación de campos, recarga y
ausencia de escrituras. Reproducir los casos de estado afectados; no repetir la
suite completa ni el recorrido de aceptación humana de I1.
