# Contrato de Pago Externo (C03 Backend)

Este documento formaliza el contrato técnico de demostración y la propuesta de
interfaz Python para la persistencia del pago externo en el módulo de gastos
(Issue #15, corte técnico C03).

> [!IMPORTANT]
> **Estado del acuerdo**: Reglas técnicas para demostración convenidas entre Franco y
> Matías sobre la base de SPEC-011 y las decisiones A–D. Este corte no constituye una regla
> institucional definitiva: las preguntas Q1–Q5 permanecen pendientes de validación
> con la operadora de Cooperadora. Franco asume el costo de rehacer la persistencia si
> la validación institucional difiere de este modelo de demo.

---

## 1. División de responsabilidades y límites de alcance

- **Gastos y Pagos (Franco, vertical propia)**:
  - Persistencia de `PagoExterno` y `EventoPagoExterno`.
  - Validación de visibilidad de gastos y de la capacidad `gastos.registrar_pago`.
  - Transaccionalidad atómica y bloqueo pesimista de la fila de gasto.
  - Normalización estricta de importes, cálculo determinista de huella SHA-256 canónica e idempotencia.
  - No altera el estado del gasto (no cierra la solicitud) ni modifica `monto_estimado`.
  - No implementa pagos parciales, transferencias bancarias, retenciones ni imputaciones contables.
  - No provee vistas, rutas HTTP ni formularios de carga en este corte (la UI depende de la
    disponibilidad de selector documental y capacidades de identidad).

- **Gestión Documental (Matías, [Issue #19](../planning/i2-issues/05-documentos.md) - Integración real pendiente)**:
  - La app y el proveedor documental de Matías **no existen en este checkout** y no han sido
    implementados aquí.
  - El módulo de gastos define un puerto consumidor (`DocumentVerificationPort` en
    [`gastos/contracts.py`](../../gastos/contracts.py)) con garantías contractuales estrictas.
  - No se implementa ningún proveedor documental productivo por defecto ni stubs tolerantes.
    Los dobles de prueba residen exclusivamente en los tests unitarios.
  - El registro del pago no devuelve ni descarga archivos; gastos no almacena binarios ni metadatos.

- **Identidad y Permisos ([Issue #21](../planning/i2-issues/02-identidad-facturacion.md) / [#28](../planning/i2-issues/09-integracion-circuitos.md) - Integración pendiente)**:
  - La extensión de identidad debe incorporar capacidades independientes:
    `documentos.incorporar`, `documentos.ver_metadatos`, `documentos.descargar` y
    `gastos.registrar_pago`. Aún no existen todas en el catálogo del adaptador de demo;
    este corte no modifica `identidad`.
  - El servicio de pagos verifica el código `gastos.registrar_pago` y, mientras la
    extensión no esté implementada, la autorización se simula en las pruebas sin
    alterar `identidad`.
  - La visibilidad de gastos se sigue resolviendo con las capacidades existentes
    `gastos.consultar_propias`/`gastos.consultar_todas` según SPEC-002, siempre sobre
    la solicitud concreta.
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
- **Referencia externa**: `CharField(max_length=128)` con limpieza de espacios (trim), obligatoria,
  estrictamente de tipo `str`.
- **Referencia documental**: `CharField(max_length=255)` que almacena un identificador opaco e
  inmutable entregado por el proveedor de documentos, estrictamente de tipo `str`.
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

---

## 4. Puerto de Integración Documental (`DocumentVerificationPort`)

El módulo de gastos define en [`gastos/contracts.py`](../../gastos/contracts.py) el protocolo:

```python
class DocumentVerificationPort(Protocol):
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
    importe: Any,
    fecha_pago: Any,
    referencia_externa: Any,
    referencia_documental: Any,
    document_provider: DocumentVerificationPort | None = None,
) -> PagoExterno:
    ...
```

### 5.2. Consulta Pura de Pago Visible
```python
def consultar_pago_externo(
    actor: Any,
    solicitud_id: int,
) -> PagoExternoConsulta | None:
    ...
```

- **DTO de Consulta**: [`PagoExternoConsulta`](../../gastos/payments.py) contiene los datos del
  pago y del evento (`id`, `solicitud_id`, `importe`, `moneda`, `fecha_pago`, `referencia_externa`,
  `fecha_registro`, `actor_id`).
- **Garantía de privacidad**: Omite deliberadamente la referencia documental para evitar
  filtrarla en respuestas genéricas de consulta.
- **Comportamiento ante solicitudes ajenas o sin pago**: Retorna `None` de forma segura sin
  revelar existencia a terceros.

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
> Los límites de la demostración aceptados por Franco **no validan** Q1–Q5. Este corte
> tampoco implementa SSO, pagos bancarios, cierres, pagos parciales, retenciones ni
> supuestos institucionales, y no agrega vistas, formularios, rutas ni plantillas.
> El proveedor documental ([#19](../planning/i2-issues/05-documentos.md)) y la extensión
> de identidad ([#21](../planning/i2-issues/02-identidad-facturacion.md) /
> [#28](../planning/i2-issues/09-integracion-circuitos.md)) permanecen pendientes.
