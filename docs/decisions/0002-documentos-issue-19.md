# Decisiones técnicas aprobadas para el primer tramo de #19

- Fecha de confirmación: 16/10/2026.
- Fuente: `Decisiones Issue #19.md`, aportado por Matías y confirmado como
  decisiones aprobadas en la conversación de trabajo.
- Autoridad de diseño: equipo de desarrollo. Cooperadora comunica necesidades
  operativas; el equipo puede reformular estas decisiones si cambian esas
  necesidades. Esta confirmación no atribuye una aprobación técnica a Cooperadora
  ni extiende la aprobación de Franco de la PR #47 a este nuevo diff.
- Alcance: DOC-R01–R03 de M-E04. DOC-R04 (#24) e integración de ambos circuitos
  (#22/#28) conservan sus entregables propios.

## Política de archivo

- Tamaño: de 1 a `10 * 1024 * 1024` bytes inclusive por archivo. La configuración
  `DOCUMENTOS_MAX_UPLOAD_SIZE_BYTES` permite ajustar el máximo sin migrar datos.
- Formatos: `.pdf`/`application/pdf`, `.jpg` o `.jpeg`/`image/jpeg` y
  `.png`/`image/png`. Extensión, MIME declarado y firma del contenido deben
  concordar. No se admiten ZIP/RAR, ejecutables, scripts ni formatos editables.
- Los archivos permanecen en almacenamiento privado y sólo se sirven mediante
  una operación autorizada.

## Clasificación y cardinalidad

Cada trámite admite múltiples documentos, incluso varios del mismo tipo para
conservar reemplazos y registros históricos. No existe una unicidad rígida por
trámite y tipo. Los catálogos `Documento.Tipo` y `Documento.Procedencia` y la
matriz del servicio restringen las nuevas incorporaciones:

| Circuito | Tipo | Procedencia válida | Cantidad esperada |
|---|---|---|---|
| Gastos | `PRESUPUESTO` | `SOLICITANTE` | 0 a N |
| Gastos | `FACTURA_PROVEEDOR` | `SOLICITANTE`, `INTERNO_COOPERADORA` | 1 a N al cierre F-E08 |
| Gastos | `TICKET_PROVEEDOR` | `SOLICITANTE`, `INTERNO_COOPERADORA` | 0 a N; respaldo adicional |
| Gastos | `COMPROBANTE_PAGO` | `EXTERNO_BANCO` | 1 a N, por ejecución F-E07 |
| Gastos | `CONSTANCIA_RETENCION_ATP` | `EXTERNO_ATP` | 0 a N, condicional |
| Facturación | `FACTURA_EMITIDA` | `EXTERNO_XUBIO` | 1 a N en M-E06 |
| Facturación | `NOTA_CREDITO`, `NOTA_DEBITO` | `EXTERNO_XUBIO` | 0 a N |
| Facturación | `COMPROBANTE_COBRO` | `SOLICITANTE`, `EXTERNO_BANCO` | 1 a N según M-E07 |

Las cantidades mínimas se comprueban en las operaciones de etapa o cierre de
cada circuito, cuando existan; la carga común no convierte por sí sola un
documento en aprobado ni cierra un trámite. El catálogo de facturación queda
definido, pero su escritura no se habilita hasta que exista su resolver y su
relación protegida con la solicitud.

La revisión de Franco en la PR #48 precisó la clasificación de la fila original
«factura / ticket» para respetar C01: `FACTURA_PROVEEDOR` designa sólo facturas;
`TICKET_PROVEEDOR` conserva tickets como documentos adicionales, pero queda
fuera de las opciones elegibles para registrar un pago. El mínimo de factura
para F-E08 no se satisface con un ticket. El proveedor C01 real aún no existe;
su implementación y verificación corresponden a #22/#28.

## Trámite y permisos

La referencia lógica combina circuito e identificador. La opción de integridad
elegida es la A del documento fuente: vínculos con FK protegidas y, al crear la
cabecera compartida en I01/#22, una entidad base para ambos circuitos. El primer
tramo conserva la FK inmutable a `SolicitudGasto`; no acepta referencias de
facturación antes de que exista su modelo. El registro genérico sin FK de la
opción B no se adopta en esta etapa porque degradaría la integridad del contrato
A01 acordado con Franco. I03/#28 verificará ambos consumidores.

Se usan `documentos.incorporar`, `documentos.consultar_metadatos` y
`documentos.recuperar_contenido`, siempre junto al acceso al trámite. Un
solicitante sólo incorpora `SOLICITANTE` en un trámite propio y con un tipo
admitido. El personal con acceso global al circuito puede incorporar
procedencias externas o internas admitidas por la matriz. No puede declarar
`SOLICITANTE` por cuenta propia. Las capacidades históricas
`documentos.ver_metadatos` y `documentos.descargar` siguen como alias en la demo
para los consumidores de gastos ya integrados; el componente nuevo exige los
códigos aprobados. La falta de capacidad devuelve 403; un trámite ajeno o
inexistente devuelve 404 sin revelar metadatos ni contenido.

## Fallos y límites

El servicio valida autorización y política antes de escribir. Guarda archivo y
metadatos dentro de `transaction.atomic()` y borra el archivo si falla una
escritura o la creación del registro. Esa compensación cubre errores dentro de
la operación; una reversión posterior de una transacción exterior puede dejar
un archivo privado huérfano. El recorrido HTTP actual usa autocommit. Si un
consumidor futuro incorpora documentos dentro de una transacción mayor, deberá
resolver ese caso antes de habilitarlo.

Los registros sintéticos creados antes de este cambio conservan sus valores
históricos de tipo y procedencia. Los catálogos se aplican a las nuevas cargas;
una reclasificación de datos previos necesita una decisión explícita sobre cada
registro, no una conversión automática de `respaldo` a otro tipo.
