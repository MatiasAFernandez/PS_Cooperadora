# I1 — paquete de trabajo para revisión

Fecha: 17/09/2026. Estado: preparación local; no se crearon Issues ni Project,
no se inició implementación y no se acredita aceptación de Cooperadora.

## Qué se prepara

Demostrar presentación de gasto → decisión humana → consulta de estado, historial
y respaldo por aportar. Usar [SPEC-001](../specs/001-demostracion-gastos.md), el tramo
de demo de [SPEC-002](../specs/002-matias-identidad-permisos.md) y el
[contrato compartido](../contracts/identidad-demo-i1.md). H1–H4 son hipótesis,
no reglas institucionales definitivas. No hay pagos, archivos ni facturación en I1.

Una tarea reúne un resultado verificable, interfaz, reglas y pruebas necesarias.
Las specs definen comportamiento; las Issues organizarán ejecución; el tablero
mostrará esas mismas Issues por estado. No copiar el contenido completo de las
specs en cada tarjeta ni convertir todas las specs de Matías en trabajo inmediato.

## Orden y dependencias

Los identificadores T01–T07 son locales, no números de Issues de GitHub. Al publicar,
registrar aquí sus enlaces; después el estado operativo se mantiene en el tablero.
No se asignan horas ejecutadas ni estimaciones sin fundamento.

| ID | Título de la futura Issue | Responsable / revisor | Dependencia | Situación inicial |
|---|---|---|---|---|
| T01 | Revisar y dejar acordado el paquete técnico de demo I1 | Franco coordina / Matías revisa identidad y contratos | Ninguna | Ready para revisión documental, no para programar |
| T02 | Proveer identidad sintética y capacidades explícitas de demo | Matías / Franco | T01 y autorización de implementación | Backlog |
| T03 | Presentar y consultar una necesidad de gasto | Franco / Matías | Inicio tras T01 y autorización; cierre tras integrar T02 | Backlog |
| T04 | Registrar decisiones humanas y conservar su historial | Franco / Matías | T02 y T03 integradas | Backlog |
| T05 | Mostrar el respaldo por aportar según la decisión | Franco / Matías | T04 | Backlog |
| T06 | Verificar y demostrar el recorrido técnico completo | Franco coordina / Matías verifica identidad y reproducción | T02–T05 integradas | Backlog |
| T07 | Validar las hipótesis con la operadora y registrar cambios | Franco coordina / Matías aporta preguntas de identidad | T06 para la demo completa; consultas pueden empezar antes | Backlog |

T02 y el trabajo propio de T03 pueden avanzar en paralelo contra el contrato revisado.
T03 no se declara terminada usando sólo dobles de prueba: debe consumir el componente
real de T02. Un desacuerdo de interfaz se resuelve en T01/contrato, no con dos
implementaciones incompatibles. No se requiere completar SPEC-002 para facturación
ni conectar el proveedor institucional para cerrar estas tareas de demo.

## T01 — revisar el paquete técnico

- Resultado: definiciones de SPEC-001, tramo de SPEC-002 y contrato consistentes.
- Aportes: Franco comprueba recorrido, titularidad y decisiones de gastos; Matías
  comprueba identidad, resolución de capacidades y límites del adaptador.
- Cierre: ambos pueden explicar cómo A, B, O y L recorren los casos; se registran
  observaciones y resolución, responsables y dependencias, sin dar H1–H4 por validadas.
- Evidencia: revisión del diff y registro de conformidad o cambios técnicos.
- Límite: revisar documentos no implementa I1. La autorización actual cubre esta
  preparación; la ejecución de código queda fuera de ella.

## T02 — identidad sintética y permisos comunes

- Requisitos: ID-R01, ID-R03 y soporte de ID-R02; CT-01 a CT-03.
- Resultado: componente común que devuelve un actor a partir de una sesión
  de demo verificada y capacidades explícitas según el contrato v1.
- Alcance: vistas estándar de acceso/salida, plantilla mínima, opción de demo
  desactivada por defecto, mapa de grupos y cuentas sintéticas reproducibles.
  No publicar credenciales fijas; preparar contraseñas locales fuera de Git.
- Pruebas: acceso válido/inválido, cuenta inactiva, salida, opción deshabilitada,
  cuenta sin asignación, grupos modificados, superusuario sin capacidades,
  datos de identidad enviados por el cliente y códigos desconocidos.
- Cierre: CT-01–CT-03 aprobados y contrato consumible por gastos sin consultar
  grupos ni credenciales desde ese módulo. Franco revisa los ejemplos de consumo.
- Evidencia: PR, pruebas y guía local de preparación de A, B, O y L.

## T03 — presentación y consulta de gastos

- Requisitos: I1-R01, I1-R02, ID-R02; H1/H2; parte de consulta de CT-04,
  CT-06 y parte de presentación de CT-08. Las acciones de decisión se prueban en T04.
- Resultado: formulario, persistencia, lista y detalle propios del circuito.
  El servidor fija solicitante, fecha y estado presentado; la unidad de prueba
  no concede acceso. Modelo con versión para las futuras decisiones de T04.
- Integración: usar actor/capacidades de T02 y las reglas de filtrado del contrato.
  Una cuenta de consulta global ve los gastos sin adquirir permiso de decisión.
- Pruebas: datos válidos e inválidos, importe positivo, asignación del solicitante,
  manipulación de campos, acceso propio/ajeno por lista y URL, ausencia de sesión.
  Comprobar también que GET o POST sin CSRF válido no crean solicitudes.
- Cierre: A presenta y consulta; B no accede a ese gasto; O y L lo consultan.
  No se crean pantallas de edición/eliminación ni carga de documentos.
- Evidencia: PR con pruebas contra PostgreSQL y recorrido reproducible de alta/consulta.

## T04 — decisión humana e historial

- Requisitos: I1-R03, I1-R04, I1-R06; H3; CT-04, CT-05, CT-07 y CT-08.
- Resultado: la cuenta autorizada acepta, posterga o rechaza desde las pantallas
  de gastos; se conservan actor, fecha, motivo y estados anterior/resultante.
- Integración: permiso explícito y visibilidad del objeto antes de decidir;
  transacción, bloqueo de fila y versión esperada conforme al contrato.
- Pruebas: cada transición admitida por SPEC-001, motivos requeridos, rechazo
  de transiciones no listadas, peticiones directas sin permiso, CSRF, GET sin
  efectos, decisión repetida y dos decisiones concurrentes sobre la misma versión.
  La prueba de concurrencia usa transacciones/conexiones independientes en PostgreSQL.
- Casos adicionales del contrato: denegar decisión propia aun combinando grupos
  y decisión sin visibilidad; rechazar acción desconocida y versión ausente o
  mal formada. Provocar un fallo al guardar el evento y verificar reversión de
  estado, versión e historial. Son controles de demo, no reglas operativas aprobadas.
- Cierre: postergar y luego aceptar conserva ambos eventos; un conflicto o error
  no deja estado parcial ni eventos adicionales. A y L no deciden el gasto de B.
- Evidencia: PR, pruebas de permisos/consistencia y consulta del historial.

## T05 — documentación pendiente de demostración

- Requisito: I1-R05; H4.
- Resultado: después de aceptar se muestra exactamente el pendiente descrito en
  H4; en las otras etapas se muestra el mensaje alternativo de esa hipótesis.
- Pruebas: presentada, postergada, aceptada y rechazada; mensaje después de recargar
  la pantalla; acceso sujeto al mismo filtrado que el detalle de la solicitud.
- Cierre: no hay carga de archivos, marca manual de conformidad, deuda por pago
  ni cierre del trámite. La etiqueta describe el ejemplo, no una obligación real validada.
- Evidencia: PR, pruebas y capturas con datos sintéticos.

## T06 — integración y demostración técnica

- Requisitos: I1-R01–I1-R06; CT-01–CT-08. ID-R04 se comprueba sólo respecto del
  consumidor gastos; la integración con facturación continúa pendiente.
- Aportes: Franco integra navegación, formularios, decisiones, historial y mensajes;
  Matías reproduce la preparación de cuentas y comprueba uso del contrato.
- Recorrido: entrar como A, presentar, entrar como O, postergar con motivo,
  aceptar después, volver como A y consultar historial/pendiente; presentar otro
  gasto y rechazarlo. Probar acceso ajeno con B y decisión denegada con L.
- Cierre: pruebas y controles automáticos aprobados; Matías reproduce el recorrido
  siguiendo la guía local. Los fallos detectados se corrigen o impiden el cierre
  si afectan los criterios. No se declara validación institucional.
- Evidencia: versión integrada, resultados de pruebas, guía y acta de demo técnica
  que identifique limitaciones y puntos para consultar a la operadora.

## T07 — devolución de la operadora

- Resultado: devolución explícita sobre H1–H4 y preguntas de permisos relevantes
  para el recorrido, sin pretender definir ahora todo el catálogo institucional.
- Aportes: Franco presenta gastos y recoge cambios de recorrido/documentos;
  Matías recoge cambios de identidad, capacidades y visibilidad.
- Cierre: registrar para cada hipótesis si fue confirmada, corregida o quedó
  pendiente, con fuente y fecha; crear tareas de ajuste cuando corresponda.
  Si quedan respuestas pendientes, no declarar aceptado todo I1. Si no hubo
  contacto o respuesta, T07 sigue abierta; no inventar una validación.
- Evidencia: minuta de devolución y vínculos a specs/tareas afectadas.

## Tablero propuesto

Un GitHub Project compartido, vinculado al repositorio, con las Issues T01–T07 y
los estados de [WORKFLOW](../WORKFLOW.md). Campos iniciales: estado, responsable,
spec vinculada e incremento. Dependencias y aceptación quedan en la propia Issue.
No hacen falta sprints, puntos, automatizaciones propias ni un documento paralelo
que copie manualmente todos los estados del tablero.

Ready exige alcance, responsable, criterio verificable y dependencias suficientes
para empezar. Un bloqueo se anota con su causa y responsable de resolverlo; no se
disfraza como trabajo en curso. Una tarea técnica puede terminar y la validación
operativa T07 continuar abierta. La IA puede preparar y ejecutar tareas autorizadas,
pero no recorrer el backlog implementando todo por el hecho de que haya specs.

## Cobertura y pendientes fuera de I1

| Requisito | Tareas que lo cubren |
|---|---|
| I1-R01 | T03, T06 |
| I1-R02 | T02, T03, T06 |
| I1-R03 | T04, T06 |
| I1-R04 | T04, T06 |
| I1-R05 | T05, T06 |
| I1-R06 | T04, T06 |
| ID-R01 / ID-R03 | T02, T04, T06 |
| ID-R02 | T03, T04, T06 |
| ID-R04 | Parcial en T06; falta el consumidor facturación en otro incremento. |

| Casos del contrato | Tarea responsable antes de la comprobación integrada en T06 |
|---|---|
| CT-01, CT-02, CT-03 | T02 |
| CT-04 | Consulta en T03; intento de decisión ajena en T04 |
| CT-05 | T04 |
| CT-06 | T03 |
| CT-07 | T04 |
| CT-08 | Presentación en T03; decisiones en T04 |

SPEC-003 a SPEC-009 conservan sus borradores y alcance futuro. En particular,
identidad institucional, permisos completos, archivos privados y pruebas de
ambos circuitos no se marcan resueltos al terminar esta demostración de gastos.
