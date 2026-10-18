# Contratos comunes de trámites, documentos e historial

Este contrato describe las interfaces entregadas en #51, #52, #55, #56 y #59.
El estado operativo se sigue en #22/#28; la evidencia está en la
[verificación de #22](../evidence/i2-22-cierre-contratos.md).

## Responsabilidades

| Dato o interfaz | Propietario | Revisor | Contrato |
|---|---|---|---|
| Cabecera y referencia | Matías | Franco | TramiteBase, TramiteRef y resolver de comunes. |
| Identidad y capacidades | Matías | Franco | resolve_actor/has_capability; acceso por objeto en cada módulo. |
| Documentos y proveedor C01 | Matías | Franco | documentos; puerto consumidor de gastos/contracts.py. |
| Solicitud, decisiones y pagos de gastos | Franco | Matías | OneToOne protegido, guardas y eventos propios. |
| Solicitud y eventos de facturación | Matías | Franco | OneToOne, presentación/observación/corrección y eventos append-only. |
| DTO y protocolo de historial | Matías | Franco | EventoHistorialDTO, sin unificar transiciones. |
| Adaptación de gastos y presentación común | Franco | Matías | como_historial(), navegación y parcial común de ambos módulos. |

## Identidad e integridad

`TramiteRef(circuito, numero_publico)` es inmutable: `gastos:7` y
`facturacion:7` son distintos. El resolver comprueba existencia y coherencia de
la solicitud y admite `circuito_esperado`. No sustituye la autorización por objeto.
`TramiteBase` conserva circuito, número público, titular y fecha. PostgreSQL
impide cambios de identidad incluso por QuerySet.update o SQL directo.
El titular usa `str(Actor.subject_id)`; centro_costo_codigo admite NULL y no
se deduce de unidad_requirente.

Ambas solicitudes tienen OneToOne protegido con cabecera. Circuito, PK/número
público y titular deben coincidir. Gastos crea solicitud y cabecera en una
transacción y aplica guardas ORM/PostgreSQL. Facturación conserva la fábrica
técnica y agrega presentación, observación y corrección con control de versión.

Se conserva por compatibilidad la FK documental original al gasto y el puente
comunes/documentos. Las nuevas solicitudes de gasto ya crean cabecera; el puente
la reutiliza y el trigger documental comprueba ambas FK. Las consultas GET no
crean cabeceras. Retirar el puente requiere un cambio compartido posterior.

## Migraciones y versiones

Las migraciones por etapas conservan PK, metadatos, rutas, bytes, autor y fechas.
Cada documento previo recibe serie y UUID de versión propios; las migraciones
no abren ni mueven archivos. Gastos agrega relación anulable, valida/vincula
cabeceras y finalmente exige NOT NULL y guardas PostgreSQL.
Su migración requiere mantenimiento por los bloqueos. Las inconsistencias
históricas abortan sin reparación automática ni transferencia de titularidad.
Las reversas se rechazan cuando perderían relaciones o datos operativos.

| Alias histórico | Código persistido |
|---|---|
| PRESUPUESTO | PRESUPUESTO_PROFORMA |
| TICKET_PROVEEDOR | TICKET_NO_FISCAL |
| FACTURA_EMITIDA | FACTURA_EMITIDA_XUBIO |
| NOTA_CREDITO | NOTA_CREDITO_XUBIO |
| NOTA_DEBITO | NOTA_DEBITO_XUBIO |

Los alias se aceptan al incorporar. Valores sin clasificación, como respaldo,
se conservan sin inferencias y no son elegibles para C01.
Cada fila es una versión inmutable. Reemplazar crea otra fila de la misma serie,
versión siguiente, UUID nuevo y vínculo protegido; conserva archivo y metadatos
anteriores. Se admiten varias series de un tipo por trámite. Reemplazo y C01
bloquean la misma raíz y el trigger SQL protege la cadena.
La referencia opaca es `str(documento.referencia_version)`.

La incorporación compensa errores internos. Presentación/corrección de
facturación usan documentos.operaciones para compensar la transacción exterior
y conservar manifiestos ante commit incierto. La
[guía de facturación](../guides/recorrido-facturacion-i2.md) explica reconciliación
con aplicación detenida. Futuros servicios de factura/cobro deben adoptar ese
contrato y verificar su rollback antes de anidar cargas. C01 sólo lee/bloquea.

## Proveedor C01 de gastos

`documentos.c01.ProveedorDocumentalGastos` implementa DocumentVerificationPort,
OpcionDocumental y DocumentoVerificado sin alterar firmas de gastos/contracts.py.

| Tipo documental | Código C01 | Elegible para pago técnico |
|---|---|---|
| FACTURA_PROVEEDOR | factura | Sí |
| PRESUPUESTO_PROFORMA | presupuesto | Sí |
| TICKET_NO_FISCAL y demás tipos | No se entregan | No |

Presupuesto/proforma están unificados: pedir exclusivamente proforma devuelve
vacío. Distinguirlos requeriría clasificación explícita. Franco aprobó el mapeo
en #51; #55 conectó el consumidor con configuración del servidor:

```python
GASTOS_PAYMENT_DOCUMENT_PROVIDER = "documentos.c01.ProveedorDocumentalGastos"
```

El setting es optativo, sin activación implícita; el cliente no elige proveedor.
Si falta o falla, el alta de pago falla cerrada. listar_opciones_para_pago es
consulta pura: exige visibilidad/metadatos y devuelve versiones vigentes y tipos
elegibles del gasto concreto. verificar_y_bloquear_documento exige transacción,
permiso de pago, visibilidad, metadatos, referencia exacta, pertenencia, tipo y
vigencia; mantiene gasto, raíz y versión bloqueados hasta terminar la transacción.
DocumentVerificationError no revela documentos ajenos. No acredita conformidad
ni devuelve cierra_deuda_documental.

El grupo demo_gastos_pago concede sólo gastos.registrar_pago; debe combinarse
con consulta/metadatos. Decidir o leer globalmente no concede escritura.
Revocar capacidades se refleja en la siguiente petición. Se conserva 404 para
objetos ajenos/inexistentes y 403 por capacidad insuficiente según el consumidor.

## Historial y navegación

EventoHistorialDTO expone evento_id, tramite_ref, tipo_evento, actor_id,
fecha_hora, estado_resultante y motivo_o_detalle. Cada módulo conserva sus
modelos/transiciones; el DTO es de lectura, sin tabla ni enum de estados común.
Facturación conserva presentación, observación y corrección sin borrar hechos.
Gastos adapta decisiones y registro de pago con actor y hora del servidor.
En el recorrido actual el pago exige gasto aceptado y ese estado es terminal;
el pago no cambia el estado. Se autoriza el trámite antes de leer su historial.

El DTO excluye referencia documental, huella de idempotencia y snapshots privados;
la plantilla escapa detalles. Ambos detalles consumen el parcial común. La
navegación ofrece rutas disponibles según capacidades y no sustituye permisos
por objeto. Véase la [guía común](../guides/historial-y-navegacion-comunes.md).

## Límites

#22 cubre modelo, contratos y evidencia de integridad/eventos. Los recorridos
completos siguen en #28 y su demostración en #29/#50. Revisión documental real
corresponde a #24; factura, cobro y cierre conservan sus issues. Carga o pago no
aprueban documentos. Aceptación de Cooperadora y almacenamiento institucional
se verifican por separado.
