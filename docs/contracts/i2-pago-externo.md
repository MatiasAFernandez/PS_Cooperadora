# Contrato de Pago Externo (C03 y formulario parcial)

Este documento formaliza el contrato técnico de demostración, la interfaz Python
de persistencia del pago externo y el consumidor web parcial en el módulo de gastos
(Issue #15, cortes C03 y S3 parcial).

> [!IMPORTANT]
> **Actualización local 04/11/2026 (v2, con ajuste UX 05/11/2026).** El pago
> registrado exige un **comprobante bancario obligatorio** (PDF, JPG, JPEG o PNG
> con validación estricta de magic bytes, extensión y MIME) en toda alta nueva. La
> constancia ATP es un documento distinto, estrictamente en formato PDF,
> obligatorio en el acto sólo si la retención es positiva y se elige adjuntarla
> ahora; puede incorporarse después mediante una acción real con pendiente visible.
> Se agregan vínculos documentales, versión efectiva e historial append-only de
> rectificaciones. Los pagos históricos sin comprobante se conservan como legado
> explícito y no se les fabrica un documento. Esta actualización pertenece a la
> rama local `feat/15-registro-pago-documentado`; no modifica C01, identidad ni
> contratos del módulo documental. La regla de banco obligatorio sustituye la firma
> histórica que permitía altas sin archivo.

> [!IMPORTANT]
> **Estado del acuerdo**: Reglas técnicas para esta demostración definidas sobre la base de
> SPEC-011 y las decisiones A–D. Este corte no constituye una regla
> institucional definitiva: las preguntas Q1–Q5 permanecen pendientes de validación
> con la operadora de Cooperadora. La demostración contempla rehacer la persistencia si
> la validación institucional difiere de este modelo técnico.

---

## 1. División de responsabilidades y límites de alcance

- **Gastos y Pagos (alcance de este corte C03)**:
  - Persistencia de `PagoExterno` y `EventoPagoExterno`.
  - Validación de visibilidad de gastos y de la capacidad `gastos.registrar_pago`.
  - Transaccionalidad atómica y bloqueo pesimista de la fila de gasto.
  - Normalización estricta de importes, cálculo determinista de huella SHA-256 canónica e idempotencia.
  - No altera el estado del gasto (no cierra la solicitud) ni modifica `monto_estimado`.
  - No implementa pagos parciales, transferencias bancarias ni imputaciones
    contables. Registra la retención informada y su constancia, sin calcular el
    impuesto ni determinar una alícuota.
  - Incluye una interfaz web de registro documentado: comprobante bancario PDF
    obligatorio, constancia ATP separada, bruto editable precargado desde el
    estimado, retención inicial cero y neto calculado en servidor. La ruta vuelve
    a validar visibilidad, permisos, estado, idempotencia y documento vigente.
  - Incluye rectificación autorizada de fecha, referencias, bruto, retención,
    neto derivado y comprobante equivocado, con motivo, versión esperada e
    historial append-only. No anula transferencias reales ni cambia beneficiario
    o cuenta.
  - Esta interfaz no reemplaza las integraciones documental ni de identidad: sin proveedor o
    permisos, la acción queda deshabilitada o devuelve un error explícito.

- **Gestión Documental ([Issue #19](../planning/i2-issues/05-documentos.md) - proveedor real integrado en [PR #51](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/51))**:
  - La aplicación documental y `documentos.c01.ProveedorDocumentalGastos` forman parte
    de la base integrada. C04 consume ese proveedor; este corte no implementa ni modifica
    el componente documental.
  - El módulo de gastos define un puerto consumidor (`DocumentVerificationPort` en
    [`gastos/contracts.py`](../../gastos/contracts.py)) con dos operaciones: listado de opciones
    de sólo lectura para el selector y verificación/bloqueo transaccional para el registro.
    El listado es provisional y nunca sustituye la comprobación autoritativa al guardar.
  - El puerto de listado devuelve referencia opaca, tipo y etiqueta segura. El proveedor debe
    limitar las opciones al gasto concreto y a los tipos admitidos; el servicio valida nuevamente
    pertenencia, tipo y vigencia dentro de la transacción.
  - El proveedor se resuelve desde `settings.GASTOS_PAYMENT_DOCUMENT_PROVIDER`; no se acepta su
    selección desde el formulario. Si no está configurado o falla, el circuito falla cerrado.
  - No se configura un proveedor por defecto ni se admiten stubs en producción. C04 consume
    el proveedor real disponible en la base; los dobles se reservan a las suites unitarias.
  - El registro del pago vincula comprobante bancario y constancia ATP como documentos
    del trámite. La pantalla y el detalle muestran nombre/tamaño y enlaces de descarga
    sólo bajo las capacidades documentales correspondientes; el endpoint real
    reautoriza `documentos.recuperar_contenido`. Gastos no almacena binarios en el
    pago: conserva las FKs y la representación original de sus hashes.

- **Identidad y Permisos ([Issue #21](../planning/i2-issues/02-identidad-facturacion.md) / [#28](../planning/i2-issues/09-integracion-circuitos.md) - adaptador de demo disponible; integración productiva y conjunta pendiente)**:
  - El adaptador de demo existente en `identidad.services.GROUP_CAPABILITIES` define
    capacidades independientes para pago y documentos, incluidas `gastos.registrar_pago`,
    `documentos.incorporar`, `documentos.ver_metadatos` y `documentos.descargar`. C04 usa
    esos grupos; esta rama no modifica `identidad` ni incorpora autenticación productiva o SSO.
  - El servicio de pagos verifica `gastos.registrar_pago`. La integración C04 usa sesiones
    Django y el adaptador de demo existente; las pruebas unitarias conservan sus fixtures y
    dobles controlados. Esto no acredita autorización institucional ni completa #21/#28.
  - La visibilidad de gastos se sigue resolviendo con las capacidades existentes
    `gastos.consultar_propias`/`gastos.consultar_todas` según SPEC-002, siempre sobre
    la solicitud concreta.
  - Para confirmar un alta nueva, la vista exige por separado
    `gastos.registrar_pago`, `documentos.ver_metadatos` (listado C01),
    `documentos.incorporar` y `gastos.consultar_todas` (clasificación documental
    vigente). La pantalla puede abrirse en modo deshabilitado para explicar el
    camino si faltan las capacidades de incorporación. La resolución del reenvío
    en el servicio C03 en sí no recibe proveedor y no lista ni verifica documentos,
    necesitando únicamente reautorizar `gastos.registrar_pago`. La rectificación de
    datos sólo exige `gastos.registrar_pago` y visibilidad; reemplazar o incorporar
    un PDF agrega las capacidades documentales.
  - `gastos.decidir` **no concede** `gastos.registrar_pago`. Registrar un pago tampoco
    concede `documentos.ver_metadatos` ni `documentos.descargar`; cada operación requiere
    su capacidad y autorización propia sobre el gasto/documento correspondiente.

---

## 2. Modelo de datos y garantías de integridad

### 2.1. `PagoExterno`
- **Vínculo con gasto**: Relación OneToOne protegida (`on_delete=models.PROTECT`) hacia
  [`SolicitudGasto`](../../gastos/models.py).
  - Límite técnico acordado para la demo: a lo sumo un registro de pago por solicitud aceptada.
  - No permite reasignación de vínculo ni borrado de solicitudes con pagos vinculados.
- **Importe**: `DecimalField(max_digits=12, decimal_places=2)` estrictamente positivo (`> 0`).
  - Restricción CheckConstraint en base de datos: `pago_externo_importe_positivo`.
  - Validación de aplicación: sólo `Decimal` o string decimal ASCII sin exponente; rechaza `bool`,
    `float`, `int`, valores no finitos, fracciones con más de 2 cifras decimales y desbordamiento
    sobre 12 dígitos (`Decimal("9999999999.99")`).
- **Moneda**: Fija en `ARS`. Restricción CheckConstraint en base de datos: `pago_externo_moneda_ars`.
- **Fecha del hecho**: `DateField` que captura la fecha real del hecho económico. Rechaza `datetime`.
  No se impone ninguna política artificial de fecha futura.
- **Referencia externa**: `CharField(max_length=128)` con limpieza de espacios (trim),
  opcional desde v2. Puede quedar vacía; no se inventa un número bancario ni se usa
  el hash del PDF o el identificador interno como referencia.
- **Referencia documental**: `CharField(max_length=255)` que almacena un identificador opaco e
  inmutable entregado por el proveedor de documentos, estrictamente de tipo `str`.
  Sigue siendo el respaldo comercial C01 y no se reasigna al rectificar el pago.
- **Comprobante bancario**: FK protegida a `documentos.Documento` (tipo
  `COMPROBANTE_PAGO`, procedencia `EXTERNO_BANCO`). Es obligatoria en toda alta
  nueva; queda nula únicamente en registros históricos migrados. El archivo admite
  PDF o imagen (JPG, JPEG, PNG) con validación real de servidor (magic bytes,
  extensión y MIME: `application/pdf`, `image/jpeg`, `image/png`), conservando
  los límites de archivo de 10 MiB; no admite WebP ni formatos no autorizados.
- **Constancia ATP**: FK protegida separada a `documentos.Documento` (tipo
  `CONSTANCIA_RETENCION_ATP`, procedencia `EXTERNO_ATP`). Conserva su regla
  estricta de PDF (firma `%PDF-`). No se infiere ni se fabrica. Con retención
  positiva puede adjuntarse ahora o incorporarse después; con retención cero no
  corresponde.
- **Versión efectiva**: entero positivo en `PagoExterno.version`. Cada
  rectificación o aporte posterior crea una fila `PagoExternoCambio` y
  incrementa la versión. La fila efectiva es la que leen el detalle y los
  reportes existentes.
- **Representación original**: `PagoExternoOriginal` conserva una sola vez los
  valores normalizados y los SHA-256/identificadores de los documentos del alta.
  Los reenvíos se comparan contra esa representación, nunca contra importes
  corregidos ni contra una huella histórica recalculada.
- **Huella de idempotencia**: `CharField(max_length=64)` que almacena el hash SHA-256 canónico
  de los valores normalizados del pago. No requiere índice UNIQUE redundante porque `solicitud`
  ya es única en esta demo.

### 2.2. `EventoPagoExterno`
- Autoridad exclusiva para la auditoría del registro: almacena el `actor` del servidor y la
  fecha/hora del servidor (`fecha_hora`), evitando duplicar estos atributos en `PagoExterno`.
- Relación OneToOne con `PagoExterno` y `on_delete=models.PROTECT` para retener historial ante
  cualquier intento de borrado.
- Tipo de evento: `pago_externo_registrado`.
- **Inmutabilidad del evento**: después de crearlo no se modifican ni el pago asociado, ni el
  actor, el tipo o la hora de registro. Tampoco se permite borrar el evento por el modelo,
  `QuerySet.delete()` o SQL directo. Las guardas ORM cubren `save()`, `clean()`, `update()` y
  `bulk_update()`; triggers PostgreSQL cubren `UPDATE` y `DELETE` por fila.
- No utiliza `DecisionGasto` ni esquemas genéricos de auditoría JSON.

Las garantías por trigger son de fila; mantenimiento privilegiado de tabla, como `TRUNCATE`, queda
fuera del contrato de la aplicación.

### 2.3. `PagoExternoOriginal` y `PagoExternoCambio`

- `PagoExternoOriginal` es OneToOne con el pago y append-only. Guarda fecha,
  bruto, retención, neto, referencias, IDs y SHA-256 de los documentos del alta,
  más `es_legado`. La migración crea una fila para cada pago previo sin inventar
  archivos ni hashes.
- `PagoExternoCambio` guarda `numero_version` resultante, tipo, motivo
  obligatorio, actor, fecha/hora del servidor, snapshots JSON cerrados
  antes/después y vínculos documentales anterior/nuevo. Es append-only por ORM y
  triggers PostgreSQL; la unicidad `(pago, numero_version)` evita duplicados.
- Los tipos son `rectificacion`, `comprobante_reemplazado`,
  `comprobante_incorporado`, `atp_incorporada` y `atp_retirada`.
- No se crea un segundo pago, no se modifica el evento original y no se recalcula
  la huella de idempotencia del alta.

---

## 3. Garantías de concurrencia e idempotencia

1. **Bloqueo Pesimista en Transacción Atómica**:
   El servicio [`registrar_pago_externo`](../../gastos/payments.py) ejecuta bajo `@transaction.atomic`.
   Adquiere un bloqueo pesimista `select_for_update()` sobre la fila de `SolicitudGasto` visible.
   - **Precedencia de visibilidad**: Si el gasto no es visible para el actor, el servicio lanza
     `PaymentExpenseNotFoundError` (HTTP 404), impidiendo descubrir la existencia de solicitudes
     ajenas antes de evaluar permisos (HTTP 403).
   - **Estado exigido**: Sólo solicitudes en estado `aceptada` admiten registro de pago.

2. **Orden de Bloqueo Transaccional**:
   Primero se bloquea la solicitud de gasto visible; posteriormente, sólo si se trata de un registro nuevo,
   se valida la dependencia e invoca al proveedor documental para bloquear pesimistamente la versión del
   documento hasta el final de la transacción.

3. **Reenvíos e Idempotencia**:
   Se computa la huella canónica mediante serialización JSON ordenada sin ambigüedad:
   `{"fecha_pago": "...", "importe": "...", "moneda": "...", "referencia_documental": "...", "referencia_externa": "...", "solicitud_id": ...}`
   - **Reenvío idéntico**: Si ya existe un pago asociado y coinciden tanto la huella como todos los
     campos normalizados (`importe`, `moneda`, `fecha_pago`, `referencia_externa`, `referencia_documental`),
     se retorna el pago existente tras reautorizar. **No se requiere ni invoca al proveedor documental**
     y **no se duplican eventos** en auditoría.
   - **Conflicto de contenido**: Si existe un pago previo pero difiere en alguno de sus datos, se rechaza
     la operación emitiendo `PaymentConflictError` (HTTP 409).

4. **Atomicidad de Escritura**:
   `PagoExterno` y `EventoPagoExterno` se persisten conjuntamente. Cualquier fallo en la creación
   del evento produce el rollback completo de la transacción.

5. **Registro documentado y compensación (v2)**:
   El alta nueva exige un PDF bancario y usa `documentos.operaciones.operacion_documental`
   como transacción exterior, con `documentos.services.incorporar(..., _escrituras=...)`
   para banco y ATP. Si falla la validación del segundo archivo, la escritura SQL o la
   creación del evento, se revierte la transacción y se compensan los archivos del
   manifiesto. No se anida una transacción exterior adicional. Las pruebas HTTP que
   recorren el alta usan `transaction=True`.
   Un reenvío idéntico al alta original se resuelve bajo el bloqueo de la solicitud,
   sin volver a exigir C01, proveedor ni PDF. Un reenvío con datos distintos produce
   conflicto. La representación original no se modifica al rectificar.

6. **Rectificación y ATP posterior (v2)**:
   Cualquier operador con `gastos.registrar_pago` y visibilidad puede rectificar
   datos. Reemplazar o incorporar un PDF exige además `documentos.incorporar` y
   `gastos.consultar_todas` por la clasificación documental vigente; no se amplía
   el contrato de documentos. La descarga sigue exigiendo
   `documentos.recuperar_contenido` en el endpoint real. La versión esperada
   serializa la concurrencia; un reenvío exacto de la misma rectificación o aporte
   se reconoce sin duplicar documentos, cambios ni eventos.

---

## 4. Puerto de Integración Documental (`DocumentVerificationPort`)

El módulo de gastos define en [`gastos/contracts.py`](../../gastos/contracts.py) el protocolo:

```python
class DocumentVerificationPort(Protocol):
    def listar_opciones_para_pago(
        self,
        *,
        actor: Any,
        gasto: SolicitudGasto,
        tipos_admitidos: Collection[str] = ("factura", "presupuesto", "proforma"),
    ) -> Collection[OpcionDocumental]:
        ...

    def verificar_y_bloquear_documento(
        self,
        *,
        actor: Any,
        gasto: SolicitudGasto,
        referencia_documental: str,
        tipos_admitidos: Collection[str] = ("factura", "presupuesto", "proforma"),
    ) -> DocumentoVerificado:
        ...
```

El selector no incluye archivos, rutas, hash ni estado de revisión. El listado debe ser puro y
devolver sólo documentos del gasto consultado; la ruta de pago no trata ese listado como una
autorización definitiva. Al enviar el formulario, el servicio revalida y bloquea la versión
vigente dentro de la misma transacción que crea pago e historial.

### Exigencias al proveedor de documentos ([Issue #19](../planning/i2-issues/05-documentos.md))
- Debe operar dentro de la transacción activa de Django iniciada por el servicio de pago.
- El método retorna únicamente tras confirmar que la versión referenciada es la versión vigente del
  documento.
- Debe verificar existencia, versión inmutable vigente y pertenencia obligatoria (FK) exclusiva al gasto.
- Debe validar que el documento sea de un tipo admitido (`factura`, `presupuesto`, `proforma`).
- La lista de tipos es fija para esta demo y el servicio de gastos no permite que quien lo invoque
  la amplíe.
- Retiene el bloqueo pesimista a nivel de base de datos hasta el commit o rollback de la transacción.
- Retorna una evidencia `DocumentoVerificado(solicitud_id, referencia_documental, tipo_documento)`
  con la referencia inequívoca al gasto (`solicitud_id`; `gasto_id` se conserva como alias de
  lectura). El servicio de pagos valida que dicha evidencia corresponda exactamente al gasto
  bloqueado, a la referencia solicitada y al tipo admitido.
- No debe exponer el archivo binario ni metadatos sensibles al módulo de gastos.
- En este recorrido técnico, una revisión que el proveedor informa explícitamente como desconocida
  no impide registrar el pago. Eso no
  equivale a aprobación documental ni satisface por sí solo la factura definitiva pendiente; el
  servicio no interpreta un estado desconocido como una decisión de aprobación.

---

## 5. Propuesta de Interfaz Python

### 5.1. Registro de Pago Externo
```python
def registrar_pago_externo(
    *,
    actor: Any,
    solicitud_id: int,
    monto_bruto: Any,
    fecha_pago: Any,
    referencia_documental: Any,
    monto_retencion_atp: Any = Decimal("0.00"),
    referencia_externa: Any = "",
    referencia_atp: Any = "",
    comprobante_bancario: Any = None,
    constancia_atp: Any = None,
    incorporar_atp_despues: bool = False,
    document_provider: DocumentVerificationPort | None = None,
) -> PagoExterno:
    ...
```

`importe` se deriva como `monto_bruto - monto_retencion_atp`; el parámetro
histórico `importe` sólo se conserva como comprobación opcional de consistencia.
El comprobante bancario es obligatorio para un alta nueva. `document_provider`
no se exige en un reenvío idéntico.

### 5.1.1. Rectificación y ATP posterior
```python
def rectificar_pago_externo(
    *, actor, solicitud_id, version_esperada, motivo, fecha_pago,
    referencia_documental=None, monto_bruto=None,
    monto_retencion_atp=Decimal("0.00"), referencia_externa="",
    referencia_atp="", comprobante_bancario=None,
) -> PagoExterno: ...

def incorporar_constancia_atp_posterior(
    *, actor, solicitud_id, version_esperada, motivo, constancia_atp,
) -> PagoExterno: ...
```

Ambas operaciones son idempotentes ante una respuesta perdida si coinciden
versión de partida, actor, motivo y contenido normalizado; de lo contrario
producen conflicto. No crean un pago nuevo ni modifican el respaldo C01.

### 5.2. Consulta Pura de Pago Visible
```python
def consultar_pago_externo(
    actor: Any,
    solicitud_id: int,
) -> PagoExternoConsulta | None:
    ...
```

- **DTO de Consulta**: [`PagoExternoConsulta`](../../gastos/payments.py) contiene los datos del
  pago y del evento (`id`, `solicitud_id`, `importe`, `moneda`, `fecha_pago`,
  `referencia_externa`, `fecha_registro`, `actor_id`, `version`, presencia de
  comprobante/constancia y pendiente ATP).
- **Garantía de privacidad**: Omite deliberadamente la referencia documental. Los
  identificadores, nombres y tamaños de los documentos sólo se completan con
  `documentos.consultar_metadatos`; la descarga se autoriza por separado en
  `documentos.recuperar_contenido`.
- **Comportamiento ante solicitudes ajenas o sin pago**: Retorna `None` de forma segura sin
  revelar existencia a terceros.

### 5.3. Interfaz web parcial de registro

- Rutas del corte: `GET/POST /gastos/<id>/pagar/` (alta),
  `GET/POST /gastos/<id>/pagar/rectificar/` y `GET/POST /gastos/<id>/pagar/atp/`.
  Las tres resuelven visibilidad y permisos en servidor; las dos últimas exigen
  versión esperada y motivo.
- `GET /gastos/<id>/pagar/` lista las opciones sólo después de resolver la visibilidad del gasto
  y exigir `gastos.registrar_pago` y `documentos.ver_metadatos`.
- `POST` conserva los valores ingresados ante errores de validación o de verificación documental.
  El error documental es genérico y no expone detalles del proveedor.
- Si ya hay un pago, la resolución del servicio C03 en sí no recibe proveedor y no lista ni
  verifica documentos: contenido idéntico retorna el registro existente y contenido diferente
  responde conflicto. No obstante, una respuesta por entrada malformada que renderiza el
  detalle de un pago existente puede realizar un listado separado en C04 para proyectar la
  categoría factual bajo la capacidad `documentos.ver_metadatos`, conservando privada la
  referencia documental guardada y sin alterar la autorización del registro.
- El detalle comunica si la acción está disponible por permisos y configuración. El formulario
  desactiva el botón mientras envía; la idempotencia de C03 cubre reintentos del servidor.
- El detalle muestra comprobante bancario y constancia ATP por separado, con
  descarga sujeta al endpoint real. Un pago histórico sin PDF se rotula como
  legado y no se completa con un archivo inventado.
- Los reportes existentes leen la fila efectiva (`fecha_pago`, `monto_bruto`,
  `monto_retencion_atp`, `importe`). Una rectificación se refleja en el período
  corregido y no suma el historial como un pago adicional.
- El formulario muestra el comprobante local seleccionado con tarjeta visual y
  metadatos (admitiendo PDF, JPG, JPEG o PNG para el comprobante bancario y PDF
  para constancia ATP) y, tras el registro, enlaces autorizados a los documentos.
  La cabecera compacta identifica solicitante y CUIT/CUIL del titular de cuenta;
  el copiado de CBU ofrece confirmación accesible; los importes se formatean y
  normalizan en formato `es-AR` en cliente y servidor; y el aviso ATP y cálculo
  de neto manejan umbrales localizados y guardas contra incoherencias o
  retenciones mayores o iguales al bruto. El proveedor C01 real y los grupos de
  capacidades del adaptador de demo están disponibles en la base integrada; C04 los consume
  con configuración de servidor y no cambia identidad. No se incluye autenticación productiva,
  SSO ni validación institucional.

---

## 6. Cuestiones institucionales pendientes (Q1–Q5)

Las siguientes dudas de negocio con Cooperadora no bloquean esta demostración pero deberán
resolverse antes del paso a producción:

- **Q1 (Etapas / Datos / Unidad-Centro de costo)**: Definición precisa de las etapas de tramitación,
  los datos requeridos en cada fase y la adscripción a unidades requirentes o centros de costo.
- **Q2 (Autoridad / Suplencias / Decisión propia / Correcciones)**: Matriz definitiva de autoridades
  firmantes, régimen de suplencias formales, política institucional sobre auto-aprobación y circuito
  de subsanación o corrección de solicitudes.
- **Q3 (Parciales / Agrupados / Referencias / Retenciones / Anulación)**: Admisibilidad de pagos
  parciales o agrupados para múltiples solicitudes, reglas para referencias bancarias/comerciales,
  tratamiento de retenciones impositivas y procedimiento ante transferencias anuladas o rechazadas.
- **Q4 (Tipo documental por momento / Revisión / Reemplazos)**: Requisitos documentales según el
  momento del trámite (presupuesto vs factura definitiva), circuito formal de revisión técnica/contable
  y política de reemplazo de comprobantes observados. La tolerancia técnica a una revisión desconocida
  no resuelve esta cuestión institucional.
- **Q5 (Regularización / Cierre)**: Procedimiento de regularización de pagos provisionales pendientes de
  factura y criterios formales de cierre administrativo y contable de los trámites de gasto.

> [!NOTE]
> **Límites de la v2 local.** No se anulan transferencias reales, no se cambia
> beneficiario o cuenta y no se reasigna el respaldo comercial C01. No se
> implementa motor fiscal, OCR, antivirus, revisión documental independiente
> obligatoria, cierre automático ni ejecución bancaria. Los umbrales
> configurados no se modifican y la frontera `>`/`>=` sigue siendo una decisión
> pendiente. Los pagos históricos sin comprobante no se corrigen por backfill.

> [!NOTE]
> Los límites técnicos de la demostración **no validan** Q1–Q5. Este corte
> tampoco implementa SSO, pagos bancarios, cierres, pagos parciales, retenciones ni
> supuestos institucionales. La interfaz web parcial de C04 consume el proveedor C01 real y
> las capacidades del adaptador de demo disponibles en la base integrada. Esto no equivale a
> autenticación productiva, SSO ni autorización institucional. La revisión formal DOC-R04/Q4,
> la identidad productiva y la integración común de [#21](../planning/i2-issues/02-identidad-facturacion.md)
> y [#28](../planning/i2-issues/09-integracion-circuitos.md) permanecen pendientes.
