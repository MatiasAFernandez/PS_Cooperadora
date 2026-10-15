# I2-01 — Decisiones recibidas para la Issue #20

Registro preparado el 15/10/2026 a partir del documento local
`docs/fuentes/Issue #20 - Decisiones de diseño.md` y de la confirmación de Matías
en esta conversación. Matías indicó que Cooperadora considera estas decisiones
aceptables y suficientes por el momento, precisó **15/10/2026** como fecha de
validación y **director del proyecto** como cargo de quien la realizó, y confirmó
que Franco acordó los contratos compartidos. Franco dejó su
[acuerdo técnico A01–A05](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/20#issuecomment-6196767849)
en la Issue #20 sobre la versión `1962b63c5024e935e86de261cfdebad5085611e4`
de `main`; aclaró que no revisó este documento nuevo. No se proporcionó nombre
ni minuta separada de Cooperadora. La fuente local está excluida de Git.

## Decisiones de facturación comunicadas

| ID | Decisión comunicada | Alcance y consecuencia |
|---|---|---|
| D01 | Si se declara un pago ya presentado por banco o Mercado Pago, fecha, número de operación y archivo son obligatorios. Si no se presentó o se elige cuenta corriente, no lo son. | Validación condicional de la solicitud; el cobro informado al presentar queda **pendiente de verificación**, no acredita ingreso ni cancelación. Después, solicitante o personal de Cooperadora pueden aportar el comprobante desde el trámite. |
| D02 | Importe positivo con dos decimales y hasta 12 dígitos; CUIT de 11 dígitos con verificador; correo del destinatario validado como correo. | El correo del solicitante proviene de la identidad autenticada. El origen de ese atributo en el adaptador de identidad debe acordarse. |
| D03 | El solicitante presenta, consulta y corrige su trámite observado; personal de Cooperadora observa, registra comprobantes y revisa documentos. | La visibilidad del solicitante se limita a sus trámites. La vista por área y la facultad concreta de cierre siguen sin quedar fijadas. Acceso por URL directa también se controla en servidor. |
| D04 | Recorrido propuesto: `PRESENTADA`, `OBSERVADA`, `FACTURADA_PENDIENTE_COBRO`, `COBRADA_EN_REVISION`, `CERRADA` o `ANULADA`; sin reapertura de estados terminales. | Cada acción y evento se registran atómicamente. Falta precisar transiciones por corrección, rechazo, cobro parcial y nota de crédito. El acuerdo A04 conserva eventos propios por circuito; no impone una tabla genérica común. |
| D05 | Archivos privados, descarga autorizada, límite de 10 MB y formatos PDF/JPEG/PNG. La revisión puede quedar pendiente, aceptada u observada; un reemplazo conserva la versión anterior. | La política de cantidad y documentos exigidos en cada etapa no está detallada. La carga por sí sola no equivale a aprobación. |
| D06 | Cooperadora registra manualmente factura, nota de crédito o débito emitida en Exubio, con punto de venta, número, fecha, importe y PDF. El neto suma facturas y débitos y resta créditos. | No hay API ni emisión fiscal. La cardinalidad descrita como `1:N` y a la vez como “1 factura y eventualmente 1 nota” necesita precisión; también el alcance de la unicidad y la vinculación de cada nota. |
| D07 | Se admiten varios cobros parciales de una solicitud. Un cobro aplicado a varias solicitudes queda fuera del incremento. Se registran medio, operación, fecha, importe, descuentos y comprobante. | Falta precisar moneda, anticipos, imputación cuando hay varias facturas y documentación de retenciones/comisiones. Un cobro aportado por el solicitante requiere verificación antes de contar para el cierre. |
| D08 | Para cerrar se exige factura, neto cubierto por cobros o nota de crédito total y comprobantes de cobro aceptados. | La suma propuesta incluye importes percibidos más retenciones/comisiones; su significado contable y el tratamiento de diferencias deben verificarse con ejemplos. El documento deja sin definir qué rol concreto autoriza el cierre. |

Las decisiones del adjunto sobre pagos, estados, deuda documental y límites para
nuevas solicitudes de **gastos** se remiten al circuito de Franco. El acuerdo de
contratos compartidos confirmado por Matías no constituye aprobación de estas
reglas funcionales de gastos.

## Acuerdo técnico A01–A05 para la demo

Franco confirmó A01–A05 en su
[comentario de la Issue #20](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/20#issuecomment-6196767849).
Revisó los contratos de la versión `1962b63c5024e935e86de261cfdebad5085611e4`
de `main`, no este resumen posterior. El alcance acordado es:

| Acuerdo | Contrato de diseño confirmado | Detalle de implementación pendiente |
|---|---|---|
| A01 | La referencia combina módulo e identificador (`gastos:7` y `facturacion:7` son distintos). Cada módulo resuelve existencia y acceso; el documento pertenece a un trámite concreto, con relación protegida por FK y sin reasignación. | Representación física e integridad en #19/#22. |
| A02 | Reutilizar `resolve_actor`/`has_capability` y controlar acción y objeto en servidor. Incorporar, ver metadatos y descargar documentos son capacidades distintas; decidir no autoriza pagar. Un trámite ajeno o inexistente no revela su existencia. | Perfiles sintéticos y capacidades de facturación en #21/#28; sin atribuir SSO institucional. |
| A03 | Incorporación, metadatos, contenido y revisión son operaciones distintas. Reemplazar crea una versión nueva e inmutable; revisión desconocida no equivale a aprobación. Archivos y metadatos tienen autorización propia y no usan rutas públicas. | Política de archivos y modelo en #19/#22; revisión real en #24. El bloqueo transaccional descrito por Franco aplica al pago de gastos, no se traslada sin diseño a cobros. |
| A04 | Cada circuito conserva sus estados y modelo de eventos. Mínimo: hecho, actor, fecha/hora del servidor y referencia al trámite; una operación fallida no deja un hecho exitoso parcial. | No imponer enum ni tabla genérica. La idempotencia y conflicto que Franco detalló corresponden al pago de gastos; facturación concreta sus operaciones en #23/#27. |
| A05 | Franco implementa y prueba gastos/pagos; Matías mantiene identidad, documentos comunes y facturación. Hay revisión cruzada de interfaces y verificación conjunta en #28. | Casos de ambos circuitos deben rechazar referencias cruzadas y accesos ajenos. |

## Casos sintéticos de aceptación y rechazo

1. Solicitante A presenta una solicitud con pago declarado y los tres datos de
   comprobante. La solicitud y el ingreso preliminar quedan vinculados; el
   ingreso no cuenta como verificado. Si falta el archivo, la presentación se
   rechaza sin crear solicitud, cobro ni documento (D01).
2. Solicitante B presenta una solicitud de cuenta corriente sin comprobante.
   Luego registra un cobro parcial con archivo. El trámite no se cierra por ese
   solo registro; Cooperadora debe verificar el ingreso y el respaldo (D01, D07).
3. Un tercero intenta leer el detalle o descargar el archivo de A mediante su
   identificador directo. El servidor no entrega datos ni archivo (D03, D05).
4. Cooperadora registra una factura ficticia de 100,00, un cobro verificado de
   60,00 y otro de 40,00, ambos con documentos aceptados. El neto queda cubierto;
   sólo una identidad con capacidad de cierre podría finalizar el trámite
   (D06–D08). El rol de esa capacidad sigue pendiente.
5. Una nota de crédito que reduce el neto a cero permite evaluar la salida
   `ANULADA`; la transición exacta y el respaldo exigido siguen pendientes
   (D04, D06, D08).

Estos casos son ejemplos de diseño con datos ficticios, no evidencia de pruebas
ejecutadas ni de una aprobación individual de Cooperadora.

## Detalles diferidos con responsable

| Pendiente | Responsable de resolver | Bloquea principalmente |
|---|---|---|
| Nombre o minuta de la validación, versión vigente del formulario y ejemplos anonimizados cobrado/pendiente | Matías y Cooperadora | #23 y evidencia posterior |
| Confirmar si las 13 preguntas actuales siguen siendo obligatorias, catálogos y excepciones; origen del correo autenticado | Cooperadora; Matías para contrato de identidad | #21, #23 |
| Precisar pertenencia por persona/área, delegación y quién puede cerrar o anular | Cooperadora | #21, #23, #27 |
| Completar estados y motivos de observación, corrección, rechazo, anulación y cobro parcial | Cooperadora | #23, #27 |
| Documentos requeridos por etapa, cantidad permitida y facultad de aportar/revisar cada tipo | Cooperadora | #19, #24–#27 |
| Aclarar múltiples facturas/notas, relación de notas, clave única con emisor y ejemplos del neto | Cooperadora | #25, #26, #27 |
| Moneda, anticipos, imputación a varias facturas, retenciones/comisiones y diferencias con ejemplos | Cooperadora | #26, #27 |
| Detalles físicos y pruebas de A01–A05, con ejemplos de ambos circuitos | Matías y Franco | #19, #21, #22, #28 |

El director del proyecto aceptó estas decisiones como suficientes por el
momento, según la confirmación de Matías del 15/10/2026. Los detalles de la tabla
quedan diferidos a sus Issues responsables; sólo bloquean la implementación que
depende de ellos. El acuerdo técnico A01–A05 consta en el comentario de Franco,
con la limitación de versión indicada arriba. Para integrar este documento y las
specs modificadas se requiere revisión de su nuevo diff; ninguna Issue de
implementación pasa automáticamente a `Ready`.
