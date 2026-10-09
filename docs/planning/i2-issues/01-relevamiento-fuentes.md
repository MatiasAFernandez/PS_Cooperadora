# I2-01 - Relevamiento inicial de facturación y contratos

Estado: evidencia registrada el 09/10/2026 para la Issue #20. No equivale a
validación posterior de Cooperadora ni a acuerdo de interfaces con Franco.

## Fuentes y alcance de la evidencia

| Fuente | Qué permite afirmar | Límite |
|---|---|---|
| [Formulario de solicitud de factura](../../fuentes/Formulario%20de%20Google%20de%20Solicitud%20de%20Facturas.md) | Nombres de preguntas, opciones visibles y 16 preguntas marcadas como obligatorias con `*`: 13 en la primera página y tres en la sección de comprobante. | La copia en Markdown no describe las condiciones de navegación entre secciones ni las validaciones de formato. |
| [Formulario de transferencia](../../fuentes/Formulario%20de%20Google%20de%20Solicitud%20de%20Transferencia.md) y [captura PDF](../../fuentes/Solicitud%20de%20Transferencia.pdf) | Ambos describen el mismo formulario actualmente utilizado; permiten identificar sus campos, la obligatoriedad visible en la captura y el adjunto de factura o proforma. | Este circuito pertenece funcionalmente a gastos/pagos de Franco. |
| [Primera entrevista](../../fuentes/transcripcion_reunion_cooperadora.md) y audio homónimo en `docs/fuentes` | Práctica actual, problemas y propuestas expresadas durante el relevamiento. | La transcripción contiene pasajes ambiguos. Una propuesta expresada en condicional no es una regla aprobada. |
| [Plan de Trabajo](../../fuentes/Plan%20de%20Trabajo.pdf) | Alcance comprometido y verificaciones RF-001/002/004/006, RNF-001 a RNF-004, M-E01/02 y C01/02. | Define el sistema a desarrollar, no completa las reglas operativas que C02 exige validar. |

`docs/fuentes` está excluido de Git; estos enlaces sirven en el checkout local,
pero no publican las fuentes en GitHub. Sólo se integra este inventario derivado.

No se incorporan respuestas reales, CUIT, correos, datos bancarios ni archivos
operativos a la documentación o a los datos de prueba. La entrevista indica que
Cooperadora prepararía recortes anonimizados de sus planillas; todavía no constan
en estas fuentes.

## Datos visibles en los formularios

**Solicitud de factura:** correo; declaración de si se presentó comprobante de
pago; nombre del solicitante; CUIT y nombre de quien recibirá la factura;
condición ante el IVA; correo de destino; detalle e importe; producto/servicio;
centro de costo; medio o cuenta indicado (incluida `Cuenta corriente`, descrita
como aún no cobrada); observaciones; y, en la sección de comprobante, fecha,
número de operación y archivo de transferencia con límite visible de 10 MB.
Las 13 preguntas de la primera página están marcadas como obligatorias en el
formulario actual: correo, comprobante presentado, solicitante, CUIT y nombre
del destinatario, condición IVA, correo de envío, detalle, importe,
producto/servicio, centro de costo, medio/cuenta y observaciones. También están
marcadas como obligatorias las tres de la sección de comprobante: fecha, número
de operación y archivo. El formulario muestra opciones para condición fiscal,
producto/servicio, centro de costo y medio/cuenta. La marca `*` no demuestra
si la sección de comprobante se muestra cuando se respondió `No` o se indicó
cuenta corriente, ni que las mismas exigencias deban copiarse sin cambios al
nuevo sistema.

**Solicitud de transferencia vigente:** correo; solicitante; titular y CUIT
de la cuenta; CBU o alias (con indicación de escribir `frecuente` para un
proveedor habitual); correo de envío del comprobante; importe; centro de costo;
observaciones; y archivo de factura o proforma. En la captura PDF esos campos
aparecen marcados como obligatorios y el adjunto tiene límite visible de 10 MB.
El Markdown y el PDF son dos representaciones de ese mismo formulario, no dos
variantes. Estos datos sirven para acordar identidad, documentos y relaciones
compartidas con Franco; no definen por sí solos los campos de facturación.

## Recorrido y responsabilidades respaldados

| Hallazgo | Tipo de evidencia | Consecuencia para las specs |
|---|---|---|
| Actualmente se usan dos formularios: uno de solicitud de factura y uno de solicitud de transferencia. El Markdown y el PDF de transferencia describen el mismo formulario. | Aclaración del responsable del 09/10/2026 y plantillas disponibles en `docs/fuentes`. | Inventariar los dos circuitos sin pedir ni modelar una variante adicional de transferencia. |
| Las correcciones tras enviar un formulario se tramitan por correo o mensajería; Cooperadora busca y reconcilia datos y documentos en formularios, planillas y carpetas. | Situación relatada en la entrevista. | SPEC-004 debe conservar observación y corrección trazables, pero falta definir quién puede realizarlas y sus estados. |
| Las facturas y notas se generan en Exubio; los comprobantes de ingreso y la factura se relacionan hoy manualmente para consulta contable. | Situación relatada en la entrevista. | SPEC-005/006 deben registrar procedencia y vínculos, sin atribuir al nuevo sistema emisión fiscal o conciliación automática. |
| Una factura emitida necesita respaldo de ingreso; el formulario admite indicar cuenta corriente todavía no cobrada. | Entrevista y formulario de factura. | Distinguir emisión de cobro/cancelación. No cerrar automáticamente al registrar factura ni exigir pago previo en todos los casos. La regla exacta sigue abierta. |
| El presupuesto puede iniciar una solicitud de pago, pero después se necesita la factura definitiva para justificarla. | Entrevista y formulario de transferencia. | Es regla del circuito de gastos; coordinar el contrato documental con Franco sin incorporarla como transición de facturación. |
| Se mencionan solicitantes de secretarías, direcciones y grupos de investigación; presidencia y tesorería para la vista administrativa. | Entrevista. | Usar estos actores como candidatos para la matriz de permisos, no como asignación definitiva de capacidades. |
| El plan exige solicitudes de factura observables/corregibles, documentos protegidos, estado e historial, y registro de facturas/notas/cobros externos hasta cierre. | Alcance definido en el Plan de Trabajo. | Mantener RF-001/002/004/006 y RNF-001/002/003/004 como restricciones de diseño; validar con Cooperadora las reglas concretas. |

El plan dispone una aplicación Django modular y registro de resultados externos
mediante la interfaz, sin integración directa con Exubio, bancos ni ATP. La
entrevista contempla la conveniencia de importar datos en el futuro; eso no
amplía el alcance definido para I2.

El apartado de antecedentes del Plan de Trabajo enumera dos formularios de
transferencia. Esa enumeración no se toma como inventario vigente: para el
relevamiento actual se sigue la aclaración de un formulario por circuito.

## Qué está decidido y qué no

- **Decidido por el plan:** Matías es responsable del circuito de facturación y
  cobros; Franco del de gastos/pagos. Identidad, documentos e historial requieren
  contratos compartidos y revisión cruzada. Las operaciones externas se
  registran; la aplicación no las ejecuta ni emite comprobantes fiscales.
- **Observado en las fuentes actuales:** campos y opciones arriba inventariados,
  herramientas utilizadas, actores mencionados y problemas de búsqueda manual.
- **Pendiente de confirmación institucional:** condiciones y validaciones de los
  campos marcados como obligatorios en el formulario de factura, y su aplicación
  en el nuevo sistema; capacidades por rol; observación y corrección; tipos y
  revisión de documentos; multiplicidad y efecto de notas; imputación de cobros;
  estados, cancelación, reapertura y cierre.
- **Pendiente de acuerdo técnico con Franco:** identificadores y propiedad de
  modelos, contrato de identidad/capacidades, documento protegido, evento de
  historial, errores y responsable de integración. La entrevista no aprueba
  estas interfaces.

La [consulta a Cooperadora](01-consulta-cooperadora.md) convierte esos pendientes
en decisiones concretas. Las respuestas se registrarán con fecha, persona que
confirma, ejemplo anonimizado y consecuencia en SPEC-002 a SPEC-009. Hasta
entonces, las pruebas podrán usar datos sintéticos, pero no presentar sus
hipótesis como reglas aprobadas.
