# I2-01 - Preguntas para validar el circuito con Cooperadora

Objetivo: cerrar las decisiones de negocio de la Issue #20 antes de fijar las
reglas de implementación. En cada respuesta registrar fecha, cargo de quien la
confirma, regla vigente, excepción y un ejemplo anonimizado. No solicitar
planillas completas ni datos personales o financieros reales por GitHub.

El [relevamiento inicial](01-relevamiento-fuentes.md) distingue lo observado en
los formularios y la entrevista de lo comprometido por el Plan de Trabajo. Las
preguntas P01-P15 son necesarias para un recorrido verificable de facturación;
P16-P18 delimitan decisiones que pueden diferirse sin bloquear la base MUST,
si Cooperadora confirma expresamente ese diferimiento.

## Preguntas necesarias para cerrar #20

### Formularios y solicitantes

| ID | Pregunta y decisión requerida | Resultado que desbloquea |
|---|---|---|
| P01 | ¿La plantilla de solicitud de factura refleja la versión vigente? ¿Pueden facilitar uno o dos trámites de facturación completos y anonimizados, uno cobrado y otro pendiente? | Inventario y ejemplos M-E01 del circuito de facturación. |
| P02 (parcial) | El formulario actual marca 16 preguntas obligatorias (13 en la primera página y tres en la sección de comprobante). ¿Se mantienen esas exigencias en el nuevo sistema? ¿Cuándo se muestra y exige la sección de comprobante si se respondió `No` o se indicó cuenta corriente? ¿Qué formatos y validaciones corresponden a CUIT, correo, importe, fecha, número y archivo? | Condiciones y validaciones de SPEC-004 y casos de rechazo; no volver a preguntar qué campos llevan `*` en la fuente. |
| P03 | ¿Qué significa cada opción de medio/cuenta, especialmente `Cuenta corriente (aun no se cobró la factura que se va a emitir)`? ¿Se admite presentar o emitir la factura sin comprobante de pago? ¿Cuándo se vuelve exigible? | Separación de solicitud, factura, cobro y cancelación. |
| P04 | ¿Los catálogos de producto/servicio, centro de costo, condición IVA y medio/cuenta se reutilizan tal como aparecen, se administran desde Cooperadora o cambian por tipo de solicitante? ¿Se permite `Otros` y con qué detalle? | Catálogos y validaciones sin copiar opciones obsoletas. |
| P05 | ¿Quién puede presentar solicitudes de factura: cualquier persona, representantes de secretarías/direcciones/grupos o usuarios designados? ¿La solicitud pertenece a una persona, a una unidad o a ambas? ¿Puede alguien actuar por otra persona? | Identidad, titularidad y visibilidad inicial. |

### Revisión, permisos y documentos

| ID | Pregunta y decisión requerida | Resultado que desbloquea |
|---|---|---|
| P06 | Para cada acción (presentar, ver, observar, corregir, registrar factura/nota, registrar cobro, revisar documento, cancelar y cerrar), ¿qué cargo o rol la realiza? ¿Quién ve todos los trámites y quién sólo los propios o los de su unidad? | Matriz de permisos RF-001/RNF-001. |
| P07 | Después de presentar, ¿cuáles son los estados y decisiones reales de la solicitud? ¿Quién puede observarla, con qué motivo, y quién puede corregir qué datos? ¿Hay límite de rondas o plazo? | Transiciones y casos de aceptación/rechazo de SPEC-004/007. |
| P08 | ¿Se permite rechazar, desistir, anular o reabrir una solicitud? ¿En qué estados y con qué motivo y autorización? ¿Qué información debe permanecer visible en el historial? | Acciones terminales, trazabilidad y reapertura. |
| P09 | ¿Qué documentos se requieren al presentar, emitir, cobrar y cerrar? Para cada tipo, ¿quién lo aporta, quién verifica su validez, cuándo queda aceptado y qué pasa al reemplazar uno erróneo? | Tipos, versiones y revisión documental RF-004. |
| P10 | ¿Qué restricciones reales de archivo deben aplicarse: formatos, tamaño, cantidad por tipo y acceso de solicitantes/operadores? El límite de 10 MB observado en Google Forms, ¿debe conservarse o es sólo una restricción de esa herramienta? | Política RNF-004 y acceso protegido. |

### Comprobantes externos, cobros y cierre

| ID | Pregunta y decisión requerida | Resultado que desbloquea |
|---|---|---|
| P11 | De Exubio, ¿qué datos identifican de forma única a cada factura, nota de crédito/débito y recibo? ¿Puede una solicitud tener varias facturas/notas? ¿Cómo se relacionan una nota y su comprobante original? | Modelo y duplicados de SPEC-005. |
| P12 | ¿Qué efecto tiene una nota de crédito o débito sobre el importe exigible, el saldo y el estado? ¿Quién verifica o registra ese efecto? | Cálculo verificable y transición de cancelación. |
| P13 | ¿Qué documento y datos prueban cada ingreso: fecha, importe, moneda, medio, número de operación, referencia bancaria/Exubio y comprobante? ¿Quién verifica que efectivamente ingresó el dinero? | Registro de cobros y evidencia de SPEC-006. |
| P14 | ¿Se admiten pagos parciales, anticipos, un cobro aplicado a varias facturas o varios cobros para una factura? ¿Cómo se distribuyen importes, retenciones, diferencias y redondeos? ¿Quién decide una excepción? | Regla de imputación y precisión monetaria RNF-002/003. |
| P15 | ¿Qué condiciones exactas definen `cancelada` y `cerrada`? ¿Se necesita cobro total, revisión documental y ausencia de pendientes? ¿Quién autoriza el cierre y puede reabrirlo? Pedimos un ejemplo que cierra y otro que debe permanecer abierto. | Estados, pendientes y cierre comprobable RF-002/006. |

## Decisiones diferibles que deben quedar delimitadas

| ID | Pregunta y decisión requerida | Tratamiento si se difiere |
|---|---|---|
| P16 | ¿Se necesitan avisos, recordatorios o restricciones a nuevas solicitudes? ¿A quién, por qué evento y con qué plazo? | Registrar prioridad y responsable; no inventar automatismos para el recorrido base. |
| P17 | ¿Qué información mínima deben ver solicitantes y personal de Cooperadora en listados, historial y reportes? ¿Qué datos sólo puede consultar presidencia/tesorería? | Separar la visibilidad MUST de filtros y resúmenes SHOULD de SPEC-008. |
| P18 | ¿Se necesitan importaciones desde Exubio, bancos o ATP en esta etapa, o basta registrar manualmente referencias y adjuntos? | Mantener el límite del plan (sin API) salvo cambio formal de alcance. |

## Acuerdos internos con Franco y Matías, no preguntas a Cooperadora

- A01: propiedad e identificador común de trámite, relaciones entre módulos y
  ejemplos válidos/denegados de ambos circuitos.
- A02: contrato de identidad recibida, capacidades por acción y resultado de
  acceso denegado, sin prometer autenticación institucional.
- A03: metadatos y acceso al documento protegido, tipos compartidos, versiones y
  revisión; distinguir reglas de facturación de la deuda documental de gastos.
- A04: evento mínimo de historial (tipo, actor, fecha y referencia), estados que
  conserva cada módulo y tratamiento de operaciones fallidas/repetidas.
- A05: responsables de implementar, revisar e integrar cada contrato y pruebas
  de interfaz con ejemplos sintéticos.

Registrar el acuerdo de A01-A05 en SPEC-009 y en los contratos afectados con
revisión cruzada. La Issue #20 permanece abierta hasta contar con respuestas a
P01-P15 o bloqueos explícitos asignados, ejemplos de aceptación y rechazo, y
acuerdo de A01-A05. Una respuesta pendiente bloquea sólo las Issues que
dependen de esa regla, según la tabla de I2.
