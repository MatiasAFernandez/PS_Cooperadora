# Cabecera común y proveedor C01: entrega de Matías para #22/#28

Actualización #21/#23 (16/10/2026): el corte de facturación consume la cabecera,
documentos y DTO sin modificar el consumidor de gastos. Agrega servicios de
presentación/observación/corrección y snapshots; conserva la fábrica técnica.
La compensación exterior se ofrece mediante documentos.operaciones y un registro
interno de escrituras en incorporar. Presentación/corrección son dueñas de su
transacción; el commit incierto se conserva para reconciliación con aplicación
detenida. Este mecanismo no conecta ni cambia el proveedor C01 de Franco.
Los límites históricos que siguen describen el corte #22 anterior; la
[guía del nuevo recorrido](../guides/recorrido-facturacion-i2.md) explica recuperación.

Base: `#22-#28.md`, aportado por Matías el 16/10/2026, con las resoluciones
confirmadas en la conversación. También se incorporan los requisitos que
Franco comunicó para conectar su consumidor. Este contrato describe la entrega
implementada; su revisión cruzada no se da por realizada.

## Propiedad y alcance

| Entrega | Responsable | Estado de este corte |
|---|---|---|
| `comunes/`: cabecera, referencias y DTO/protocolo de historial | Matías; revisión de Franco | Implementada |
| `documentos/`: migraciones, versiones, acceso y proveedor C01 | Matías; revisión de Franco | Implementada |
| Modelo mínimo y eventos propios de `facturacion/` | Matías | Infraestructura de #22; recorrido funcional en #23–#27 |
| Catálogo sintético de capacidades, incluido `gastos.registrar_pago` independiente | Matías | Implementado; asignación explícita por grupo |
| OneToOne `SolicitudGasto.tramite_base` y guardas de su identidad | Franco | Pendiente; este corte conserva la FK documental de gastos y usa un puente |
| Adaptar los eventos existentes de gastos al DTO | Franco | Pendiente; no se crea una tabla ficticia `EventoGasto` |
| Conectar y verificar el consumidor de pagos con el proveedor real | Franco | Pendiente; se entrega clase y contrato, sin activar la configuración global |
| Navegación y parcial visual de historial común | Franco; Matías aporta los DTO de facturación | Pendiente |
| Recorrido integrado de los dos circuitos | Matías y Franco | Pendiente de las entregas de cada circuito |

Las apps mantienen su ubicación actual en la raíz del proyecto. Cada módulo
Python nuevo tiene un docstring que explica su función y los comentarios
describen los puntos de autorización, migración o bloqueo que lo requieren.

## Identidad e integridad común

`TramiteRef(circuito, numero_publico)` es una referencia inmutable. Conserva
`gastos:7` y `facturacion:7` como identidades distintas, aunque coincidan los
números. El resolver consulta por ambos datos, verifica la solicitud concreta
y puede exigir un circuito consumidor mediante `circuito_esperado`.

`TramiteBase` guarda circuito, número público, titular y fecha de creación.
PostgreSQL impide cambiar esos datos aun mediante `QuerySet.update()` o SQL
directo. El titular corresponde a `str(Actor.subject_id)`; no se usa `actor.id`.
`centro_costo_codigo` admite NULL: `unidad_requirente` no se transforma en un
centro de costo supuesto.

Facturación tiene un OneToOne protegido con la cabecera. Su PK coincide con el
número público; la fábrica reserva la secuencia de PostgreSQL y crea las dos
filas juntas. Es una solicitud `BORRADOR_TECNICO`, sin formulario, factura, cobro
ni transición funcional implementada. Los eventos de facturación son
append-only y se convierten a `EventoHistorialDTO`; #23 implementará los
servicios de presentación, observación y corrección con sus reglas de estado.

Hasta la entrega de Franco, gastos conserva su esquema existente. El puente
crea cabeceras de gastos previos durante la migración y de gastos nuevos al
incorporar un documento, bajo bloqueo del gasto. Las consultas GET no crean
cabeceras. El resolver comprueba número y titular; los documentos conservan su
FK original al gasto, además de la FK a la cabecera. Un trigger rechaza enlaces
incompatibles. Si cambia el titular del gasto legado, la discrepancia con la
cabecera se deniega; no se transfiere el acceso a los documentos.

La FK desde la propia solicitud de gasto y la protección de sus cambios son la
entrega pendiente de Franco. Este puente no acredita esa parte del cierre de #22.

## Migraciones y datos anteriores

Se crean las cabeceras, se agregan campos documentales inicialmente anulables,
se migran datos y luego se vuelve obligatoria la FK documental. Cada documento
previo recibe una serie UUID y una referencia UUID de versión independientes.
Se conservan PK, ID público del gasto, autor, fechas, nombre físico, tamaño,
hash y bytes. Las migraciones nunca abren ni mueven archivos del storage.

Los códigos conocidos se traducen explícitamente:

| Anterior | Código persistido nuevo |
|---|---|
| `PRESUPUESTO` | `PRESUPUESTO_PROFORMA` |
| `TICKET_PROVEEDOR` | `TICKET_NO_FISCAL` |
| `FACTURA_EMITIDA` | `FACTURA_EMITIDA_XUBIO` |
| `NOTA_CREDITO` | `NOTA_CREDITO_XUBIO` |
| `NOTA_DEBITO` | `NOTA_DEBITO_XUBIO` |

Estos alias también se aceptan al incorporar archivos desde clientes del primer
tramo. Valores históricos no clasificados, como `respaldo`, se conservan sin
reinterpretación y no son elegibles para C01. Requieren clasificación explícita.
Los códigos describen la clasificación declarada; no prueban validez fiscal.

El rollback del nuevo esquema se admite antes de crear versiones de reemplazo
o documentos de facturación. Si existen, se rechaza la reversión a un esquema
que perdería sus relaciones; debe prepararse una migración posterior de corrección.

## Versiones documentales

Cada fila representa una versión inmutable de un archivo. Un reemplazo crea
otra fila con la misma serie, versión siguiente, UUID nuevo y vínculo protegido
con su antecesor. No modifica ni borra el archivo anterior. Un trámite puede
tener varias series del mismo tipo: no existe unicidad por trámite y tipo.

La raíz de la serie se bloquea tanto al reemplazar como al verificar C01. El
trigger SQL usa el mismo bloqueo y valida la cadena incluso si se escribe por
ORM directo. La referencia opaca de C01 es `str(documento.referencia_version)`;
identifica exactamente una versión, sin exponer el contador interno.

## Mapeo para el puerto C01 vigente

Se mantienen `DocumentVerificationPort`, `OpcionDocumental` y
`DocumentoVerificado` de `gastos/contracts.py`, con sus firmas y códigos actuales.

| Clasificación documental | `tipo_documento` entregado a C01 | Elegible para pago técnico |
|---|---|---|
| `FACTURA_PROVEEDOR` | `factura` | Sí |
| `PRESUPUESTO_PROFORMA` — incluye el alias anterior `PRESUPUESTO` | `presupuesto` | Sí |
| `TICKET_NO_FISCAL` — incluye el alias anterior `TICKET_PROVEEDOR` | No se entrega | No |
| Comprobantes de pago, retención y todos los tipos de facturación | No se entregan | No |

El catálogo persistido unifica presupuesto y proforma. Por eso el proveedor
emite `presupuesto` para ambos y no emite `proforma` como tipo independiente.
Si el consumidor pide exclusivamente `proforma`, el listado queda vacío. Una
distinción futura exige clasificación explícita; no se deduce del nombre del
archivo. Este mapeo concreto queda para revisión de Franco antes de conectar.

Ni la clasificación de factura ni una revisión desconocida acreditan conformidad
documental o contable. El proveedor no devuelve `cierra_deuda_documental` ni
cambia estados. La deuda documental y el cierre de gastos pertenecen a Franco.
DOC-R04 y la revisión real siguen en #24.

## Proveedor para conectar desde gastos

Clase: `documentos.c01.ProveedorDocumentalGastos`.

`listar_opciones_para_pago()` es una consulta pura: autoriza acceso al gasto y
metadatos, y devuelve sólo versiones vigentes del gasto concreto y tipos elegibles.
El consumidor puede reducir el catálogo, pero no ampliarlo para admitir tickets.

`verificar_y_bloquear_documento()` exige una transacción activa y comprueba
capacidad de pago, acceso al gasto, capacidad de metadatos, referencia exacta,
pertenencia, tipo y vigencia. Conserva bloqueos sobre gasto, raíz documental y
versión hasta que termine la transacción exterior. Las referencias inválidas
fallan con `DocumentVerificationError`, sin exponer datos del documento ajeno.
La verificación no escribe archivos ni confirma conformidad documental.

Franco puede configurarlo en el servidor para su integración:

```python
GASTOS_PAYMENT_DOCUMENT_PROVIDER = "documentos.c01.ProveedorDocumentalGastos"
```

El cliente no selecciona el proveedor. Este corte no configura ese setting por
defecto. Las pruebas usan el proveedor real con el servicio de pago existente,
y prueban un acceso a su formulario con sesiones reales, sin modificar `gastos/`.

`demo_gastos_pago` concede únicamente `gastos.registrar_pago`. Debe asignarse
explícitamente junto con el acceso al gasto y metadatos cuando corresponda.
`demo_operadora` conserva sus capacidades existentes y no recibe pago implícito
por `gastos.decidir`. Revocar el grupo de pago se refleja en la siguiente petición.
Facturación usa capacidades independientes de consulta propia y global; ninguna
capacidad global de lectura implica por sí sola una acción de escritura.

## Alcance de #28 y comprobación pendiente

Se conserva 404 para objetos ajenos o inexistentes y 403 cuando falta una
capacidad. Hay pruebas de metadatos y descarga de ambos circuitos, revocación,
colisión de IDs, rechazo por ticket, referencia cruzada, versión obsoleta,
idempotencia del servicio de pago y bloqueo desde conexiones independientes.

Los flujos completos de facturación de #23–#27 y los cambios de gastos y
navegación de Franco siguen pendientes. #22/#28 permanecen abiertas: esta entrega
no acredita los dos recorridos funcionales de punta a punta.

La incorporación de bytes compensa fallos dentro de su propia operación. Su
rollback exterior sigue sin resolverse; antes de anidarla en la transacción de
una factura o cobro, Matías debe implementar el mecanismo de almacenamiento
correspondiente. C01 verifica documentos ya incorporados y no tiene ese riesgo
de escritura de archivos. La configuración institucional queda fuera de esta demo.
