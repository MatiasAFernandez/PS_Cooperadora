# Referencias de Xubio sin archivo y trazabilidad — contrato v2

- Fecha: 10/11/2026. Estado: **registro sin PDF y trazabilidad manual implementados; API fuera del alcance**.
- Capacidad: [SPEC-018](../specs/018-matias-registro-externo-simplificado.md), [#76](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/76).
- Responsable del consumidor de facturación: Matías Alejandro Fernández.
- Franco Damián Sánchez revisa efectos compartidos y conserva gastos/pagos.
- Cooperadora valida los detalles operativos; Sistemas decide una eventual API.

El encargo posterior autorizó el registro manual sin PDF. Su implementación usa
comprobantes sucesores también para incorporar el primer PDF real, conservando
el registro anterior sin archivo y exigiendo revisión del PDF nuevo. No introduce
una actualización con anterior nulo. La migración 0024 agrega envío declarado y acuse voluntario del titular.

Este contrato propone cómo cumplir la necesidad de la demo sin depender de una
conexión. La migración 0023 adapta las guardas SQL al registro opcional. La
[guía de preparación](../guides/preparacion-xubio.md) documenta fuentes, campos
externos, puntos de cambio y continuidad para Sistemas. La API queda fuera del
alcance del proyecto y de esta entrega.

## Responsabilidades y límite

Xubio conserva el comprobante emitido. Facturación conserva su relación con una
solicitud, identidad fiscal, importe y trazabilidad. `documentos` conserva bytes,
versiones y revisiones únicamente cuando se aporta un archivo real. Una referencia
externa no crea un `Documento` vacío, PDF ficticio ni revisión ACEPTADO artificial.

La dispensa propuesta alcanza facturas y notas con origen `EXTERNO_XUBIO`.
`EXTERNO_OTRO`, cobros, respaldos iniciales del solicitante y gastos conservan
sus requisitos actuales. Un presupuesto de venta de Xubio no es una factura
emitida, un cobro confirmado ni un presupuesto de proveedor del circuito de gastos.

## Datos de la referencia

| Dato | Regla propuesta |
|---|---|
| Solicitud | Existente, operativa, abierta y visible para el actor. El solicitante se obtiene de su cabecera; no se vuelve a cargar. |
| Tipo | `FACTURA`, `NOTA_CREDITO` o `NOTA_DEBITO`, conservando los tipos actuales. |
| Identidad fiscal | CUIT del emisor, letra, punto de venta y número, con las validaciones y unicidad vigentes de SPEC-005. Se conserva el número completo visible para buscarlo externamente. |
| Fecha de emisión e importe | Fecha declarada del comprobante e importe decimal positivo en ARS, hasta dos decimales y el máximo vigente. No confundir emisión con registro o envío. |
| Origen | `EXTERNO_XUBIO`, fijado/validado en servidor. La dispensa se deriva del origen y la ausencia de archivo; no de una casilla libre de exención. |
| Factura de origen | Cada nota conserva el vínculo con la factura de su solicitud y compatibilidad de emisor/letra. Se mantiene una factura vigente por solicitud y varias notas. |
| Archivo | Opcional para Xubio; si se aporta, PDF real protegido con política de tamaño, versiones y revisión vigente. |
| Actor y registro | Identidad autenticada y fecha/hora del servidor; no se aceptan del CSV ni de la API como autoría local. |
| Identificación técnica Xubio | Opcional para la carga manual. Una futura asociación incluye empresa configurada, recurso e ID externo; no sustituye la identidad fiscal ni identifica una solicitud por sí sola. |

Mantener estos datos evita cambiar netos, notas y unicidad sólo para omitir bytes.
Es un perfil técnico propuesto, no una confirmación de que Cooperadora deba
transcribir todos estos campos para siempre. Reducirlos requiere revisar los
consumidores financieros y sus garantías, con aceptación propia.

## Operaciones e invariantes

1. **Registrar:** entrada = actor autenticado, solicitud, datos anteriores y PDF
   opcional. Salida = comprobante vigente e historial consultables. Se validan
   visibilidad por objeto y capacidad `facturacion.registrar_factura_externa`;
   `documentos.incorporar` sólo se exige si se incorporan bytes. La conformidad
   conjunta conserva sus permisos independientes y se ofrece sólo con PDF.
2. **Consultar:** respeta visibilidad de la solicitud y las capacidades vigentes.
   Muestra «Registrado en Xubio — archivo no requerido» cuando corresponda; no
   ofrece descarga/revisión de un archivo inexistente. Sin acceso documental no
   se revelan metadatos protegidos. No se realizan llamadas de red durante GET.
3. **Corregir:** conserva registro previo, motivo, actor y fecha; crea un sucesor
   del mismo tipo bajo las reglas actuales. Un registro histórico con PDF no
   pierde sus bytes ni su revisión. Si tiene archivo vigente, la corrección no
   puede eliminarlo para eludir una observación/rechazo. Sin archivo, la corrección
   de datos no necesita crear/copiar un PDF.
4. **Aportar un PDF después:** debe poder asociarse el primer archivo real a una
   referencia sin archivo, con autorización e historial. No usar
   `ActualizacionRespaldo` con `anterior=NULL`: hoy exige una versión anterior.
   La implementación debe definir ese primer vínculo, su revisión y su inclusión
   en la huella de concurrencia antes de habilitar la acción.
5. **Registrar envío:** declaración explícita de un envío realizado externamente,
   vinculada al comprobante/versionado exacto, con fecha de envío declarada,
   destinatario efectivo, actor y fecha/hora de registro. El correo de la solicitud
   puede proponerse, pero se confirma el destinatario real. Ausencia de evento =
   «Envío no registrado», sin inferir que no se envió. Una rectificación agrega
   un hecho con su autor y momento de registro, sin sobrescribir el anterior. No envía correo ni acredita
   entrega/lectura. Si se incluye en la misma acción de alta, ambos hechos se
   confirman o revierten juntos. El acuerdo del 10/11/2026 confirma que no es obligatorio para cerrar.

Registrar o rectificar el envío usa la misma capacidad de registro de comprobante
y autorización por objeto/estado; no requiere incorporación de archivos. No se
deduce permiso de envío de la capacidad de consultar o cerrar el trámite.

Las escrituras bloquean cabecera y solicitud en el orden vigente, revalidan
permisos/estado y guardan hechos e historial en una transacción. Si hay archivo,
usan la operación documental y sus garantías de compensación existentes. La
unicidad fiscal sigue protegida en PostgreSQL entre comprobantes vigentes,
incluidos los registrados con PDF. Un reenvío/alta concurrente produce conflicto
sin duplicar registros ni eventos. No se reasigna silenciosamente una factura a
otra solicitud.

Una asociación técnica futura es única por empresa + recurso + ID externo para
el comprobante lógico y conserva su historial de correcciones. Si ya existe su
identidad fiscal por carga manual, se propone enlazarla tras confirmación
autorizada; no crear una segunda factura ni sobrescribir sus datos. Colisiones
entre ambos identificadores requieren resolución explícita y no dejan escrituras
parciales. Sistemas definirá almacenamiento y restricciones al implementar.

## Pendientes, cierre y anulación

| Situación | Tratamiento propuesto |
|---|---|
| Referencia Xubio válida sin PDF | Satisface el registro de factura/nota. No genera pendiente por archivo ausente ni exige revisión documental inexistente. |
| Xubio con PDF aportado | Conserva revisión de su versión vinculada vigente. OBSERVADO/RECHAZADO/PENDIENTE siguen siendo impedimentos según el contrato de cierre. |
| Otro origen sin PDF | Se rechaza bajo la regla actual; no hereda la dispensa. |
| Cobro sin respaldo aceptado o sin verificación | Mantiene los controles actuales. Registrar una factura o recibir datos de Xubio no confirma ingresos. |
| Sin factura, neto no positivo, importe insuficiente, cobros pendientes u observación vigente | Mantiene los impedimentos actuales de SPEC-007. |

Aplicar la dispensa también a los controles documentales de anulación. Conservar
resolución humana explícita, capacidad independiente, huella de revisión, estados
terminales e historial. La factura sin PDF cuenta en neto y seguimiento financiero
igual que una con PDF. La indisponibilidad futura de Xubio o la falta de
credenciales no impiden el registro manual ni el cierre de una referencia válida.
La consulta de disponibilidad externa no es un requisito de negocio local.

La huella debe incorporar los nuevos hechos que afecten la resolución (referencia,
corrección, asociación inicial de archivo y revisión). Los hechos de correo no afectan condiciones ni huella del cierre. El envío
requiere trámite abierto; el acuse voluntario del titular admite terminales,
sin reabrir ni alterar la resolución.
No basta con cambiar `required=False` en un formulario: diagnóstico Python y
guardas SQL deben producir la misma decisión, incluso con escrituras directas.

## Escenarios para aceptar una implementación posterior

| Caso sintético | Resultado exigido |
|---|---|
| Factura Xubio sin PDF; cobros confirmados con respaldos aceptados y demás condiciones completas | Alta y cierre explícito posibles; sin documento/revisión ficticios. |
| Factura y notas Xubio sin PDF | Neto coherente y asociaciones conservadas; no reclaman archivos dispensados. |
| Datos inválidos, Otra procedencia sin PDF, recibo o presupuesto tratado como factura | Rechazo sin cambios parciales. |
| Factura con archivo observado/rechazado | No se puede dispensar quitando el vínculo ni cerrar por esa vía. |
| Cobro pendiente o archivo bancario inválido | Sigue bloqueado aunque la factura no requiera PDF. |
| Misma identidad fiscal manual/API; dos altas concurrentes o reenvío | Un único registro lógico; conflicto/enlace controlado, sin duplicación. |
| Acceso ajeno por URL, falta de capacidad o solicitud terminal | Denegación sin filtrar datos ni modificar hechos. |
| Corrección sin PDF y corrección histórica con PDF; primer adjunto posterior | Sucesión trazable, archivos anteriores conservados y revisión sólo del archivo real. |
| Emisión, registro y envío en fechas distintas; envío ausente o rectificado | Hechos distinguibles, destinatario confirmado y sin correo automático. |
| Vista obsoleta y fallo transaccional | Conflicto/rollback sin evento, vínculo o archivo utilizable aislado. |
| Base previa a la migración y escritura SQL directa | Históricos conservados; mismas reglas de archivo y cierre que el servicio. |

Estos escenarios definen aceptación; las verificaciones realmente ejecutadas
para el corte implementado se detallan en la guía, sin dar por probado el envío.
El encargo posterior habilitó implementar el registro sin PDF; #76 conserva
validación operativa institucional pendiente. Las verificaciones ejecutadas se
registran en la guía de preparación.

## Recepción voluntaria acordada

El botón «Confirmar que recibí este comprobante» registra al titular autenticado
sobre un envío exacto; no acredita entrega técnica ni lectura del correo. Repetir
la confirmación devuelve el mismo hecho. Un operador/lector u otro solicitante
no pueden confirmarla por el titular. Cada envío conserva destinatario, fecha
externa, actor y momento de registro; un nuevo envío no hereda la confirmación.
Las correcciones agregan otro hecho sin borrar el anterior. Si nunca se informó
un envío, se muestra «Envío no informado». Si falta acuse, se muestra recepción
sin confirmar; ambas situaciones permiten avanzar. Datos históricos no reciben
marcas de envío/recepción inferidas. Las tablas son inmutables por ORM y SQL.
