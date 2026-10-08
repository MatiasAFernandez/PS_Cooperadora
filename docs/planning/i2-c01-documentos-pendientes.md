# I2-C01 — Frontera documental del gasto: decisiones abiertas y casos de revisión

**Fecha:** 08/10/2026.
**Estado:** Borrador de revisión técnica preparatoria para S1. **No es contrato acordado, no habilita paso a Ready ni implementación, y no reemplaza las tareas humanas pendientes de I1 (T06/[#8](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/8) y T07/[#9](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/9)).**
**Marco metodológico:** [WORKFLOW](../WORKFLOW.md) y ciclo SDD en [docs/specs/README.md](../specs/README.md). Trazado al plan [i2-tareas.md](i2-tareas.md) (ficha I2-C01 / S1) y [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md).
**Límites:** No presupone acuerdos cerrados, proveedor documental de Matías implementado ([Issue #19](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/19)), ni validación institucional de Cooperadora. No repite el prototipo ni los casos sintéticos ya existentes de C02 en `.local/`.

---

## 1. Propósito y delimitación de la frontera

Este documento delimita exclusivamente los puntos de contacto que los contratos vigentes ([SPEC-002](../specs/002-matias-identidad-permisos.md), [SPEC-003](../specs/003-matias-documentos.md), [SPEC-009](../specs/009-matias-integracion-compartida.md) y [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md)) dejan técnicamente abiertos entre el módulo de **Gastos/Pagos** (Franco) y el componente común de **Documentos/Identidad** (Matías).

No reproduce la matriz completa de escenarios de S1 ni el catálogo de fixtures ya evaluados. Presenta cada propuesta de interfaz bajo la condición explícita de **propuesta no acordada**.

---

## 2. Decisiones abiertas en la frontera documental

### D1. Identificador común de trámite para vincular documentos al gasto
- **Fuentes exactas:** [SPEC-009](../specs/009-matias-integracion-compartida.md) (sección *Alcance* e `INT-R03`), [SPEC-003](../specs/003-matias-documentos.md) (`DOC-R01` y dependencias del primer tramo M-E04), [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md) (sección 4 y tabla *Contrato del consumidor*).
- **Situación en contratos:** SPEC-009 y SPEC-003 establecen que los documentos se vinculan a un identificador de trámite, pero dejan el esquema exacto de ID como diseño conjunto pendiente. En gastos, la entidad raíz actual es `SolicitudGasto`.
- **Propuesta no acordada:** Utilizar un identificador unívoco de trámite (`tramite_id`) resuelto desde la solicitud de gasto hacia el componente documental como clave de partición y autorización.
- **Casos que distinguen la decisión:**
  - *Aceptación:* Con `tramite_id` válido y coincidente con el gasto autorizado, el consumidor consulta referencias y metadatos de los documentos propios sin error.
  - *Denegación:* Si un documento tiene un `tramite_id` perteneciente a otra solicitud, el consumidor rechaza el vínculo con error `DOCUMENTO_NO_VINCULADO_TRAMITE`, sin persistir cambios ni exponer contenido (`GP-02`).
- **Respuesta humana faltante:** Acuerdo técnico conjunto Franco/Matías en SPEC-009 sobre tipo y formato del `tramite_id` compartido antes de fijar claves foráneas o tipos en el consumidor.

### D2. Desacoplamiento del aporte documental frente a la revisión (`DOC-R04`) y pendientes
- **Fuentes exactas:** [SPEC-003](../specs/003-matias-documentos.md) (sección *Primer tramo preparado para Issue* excluye `DOC-R04`), [Issue #19](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/19), [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md) (`GP-05` y supuesto `S-H4`).
- **Situación en contratos:** M-E04 (Issue #19) cubre incorporación, metadatos y acceso (`DOC-R01`–`DOC-R03`), pero excluye formalmente la revisión documental (`DOC-R04`) hasta definir reglas institucionales. Gastos necesita proyectar si la documentación de un pago está pendiente o aportada sin dar por válida una revisión inexistente.
- **Propuesta no acordada:** El consumidor de gastos mantiene desacoplados el hecho de aporte y la revisión:
  1. Si el respaldo es proforma: `aporte_documental = "pendiente_definitiva"`.
  2. Si se aporta factura: `aporte_documental = "aportado"`.
  3. Para todo documento sin revisión formal implementada: `revision_documental = "unknown"` y `conformidad_contable = "sin_conformidad"`. La mera presencia de un archivo nunca satisface el pendiente ni concede conformidad contable implícita.
- **Casos que distinguen la decisión:**
  - *Aceptación:* Gasto aceptado con pago y factura aportada se proyecta con documento visible, pero estado de revisión `unknown` y trámite no cerrado (`GP-01`, `GP-05`).
  - *Denegación:* Un documento aportado sin acto de revisión no puede marcar el pendiente como `satisfecho` ni mutar `SolicitudGasto.estado` a cerrado.
- **Respuesta humana faltante:** Validación de Cooperadora sobre regla institucional de revisión Q4 (quién, cómo y cuándo valida un comprobante) y definición de Matías de la interfaz futura de `DOC-R04` en I03.

### D3. Granularidad y denominación de capacidades para consulta y vinculación documental
- **Fuentes exactas:** [SPEC-002](../specs/002-matias-identidad-permisos.md) (`ID-R03`, `ID-R04`), [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md) (supuesto `S-H2`, tabla de capacidades y notas de sección 3).
- **Situación en contratos:** SPEC-002 establece capacidades explícitas en servidor para I1 (`gastos.solicitar`, `gastos.decidir`, `gastos.consultar_todo`), pero no define capacidades para consultar documentos ni para asociar comprobantes a pagos en I2. SPEC-011 prohíbe inferir permisos documentales o de pago a partir de `gastos.decidir` o de consulta global.
- **Propuesta no acordada:** Definir capacidades candidatas provisionales (`gastos.documento.consultar` y `gastos.pago.registrar_candidata`) a nivel de interfaz de servicio interno, verificadas siempre en el servidor.
- **Casos que distinguen la decisión:**
  - *Aceptación:* Usuario con capacidad de registro y pertenencia sobre el trámite vincula el comprobante y genera el registro del hecho.
  - *Denegación:* Usuario con rol de consulta global sin capacidad de pago intenta registrar o asociar comprobante: el sistema rechaza con `CAPACIDAD_INSUFICIENTE` sin exponer metadatos del trámite ajeno (`GP-02`).
- **Respuesta humana faltante:** Acuerdo técnico Franco/Matías sobre nombres e integración en el adaptador de identidad ([SPEC-002](../specs/002-matias-identidad-permisos.md)), y validación institucional de Cooperadora sobre la matriz de autoridad Q2.

### D4. Ciclo de incorporación del comprobante y consumo de referencias
- **Fuentes exactas:** [SPEC-003](../specs/003-matias-documentos.md) (`DOC-R02`, sección *Módulos e interfaces*), [SPEC-009](../specs/009-matias-integracion-compartida.md) (`INT-R02`), [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md) (sección 4 *Contrato del consumidor*).
- **Situación en contratos:** Gastos no implementa almacenamiento de archivos ni endpoints multiparte propios. El componente de documentos gestiona la persistencia física y validación de tipos/tamaños. Queda abierto si gastos recibe un identificador documental preexistente (`comprobante_doc_id`) o si orquesta la carga mediante una llamada interna.
- **Propuesta no acordada:** Separación en dos fases: el archivo se incorpora previamente en el componente documental obteniendo una referencia válida (`comprobante_doc_id`); la operación de registro de pago en gastos consume únicamente esa referencia, validando existencia, pertenencia al trámite y política admisible de tipo (`'proforma'`, `'factura_definitiva'`, `'recibo'`, `'unknown'`).
- **Casos que distinguen la decisión:**
  - *Aceptación:* `comprobante_doc_id` existente y asociado al mismo trámite permite registrar el pago en forma atómica.
  - *Denegación:* Referencia inexistente o documento rechazado por política de tamaño/tipo en el componente documental provoca rechazo total (`DOCUMENTO_NO_ENCONTRADO` o `DOCUMENTO_INVALIDO`) sin registrar pago parcial ni eventos residuales (`GP-04`).
- **Respuesta humana faltante:** Acuerdo de interfaz entre Franco y Matías para la llamada interna de validación/recuperación en SPEC-009, y respuesta institucional Q4 sobre tipos de comprobantes y tamaño máximo tolerado.

---

## 3. Matriz de trazabilidad de respuestas humanas requeridas

| Decisión abierta | Interfaz / Contrato involucrado | Acuerdo técnico pendiente (Franco / Matías) | Validación institucional pendiente (Cooperadora / Q1-Q5) |
|---|---|---|---|
| **D1: Identificador común de trámite** | [SPEC-009](../specs/009-matias-integracion-compartida.md), [SPEC-003](../specs/003-matias-documentos.md) | Formato y tipo de `tramite_id` | N/A (decisión técnica de arquitectura) |
| **D2: Desacoplamiento aporte vs. revisión** | [SPEC-003](../specs/003-matias-documentos.md), [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md) | Interfaz de consulta de estado/revisión en I03 | **Q4**: Regla de revisión, quién revisa y qué valida conformidad |
| **D3: Capacidades de acceso y pago** | [SPEC-002](../specs/002-matias-identidad-permisos.md), [SPEC-011](../specs/011-franco-seguimiento-pago-externo.md) | Nombres de capacidades en `gastos.auth` / identidad | **Q2**: Matriz formal de autoridad y delegaciones operativas |
| **D4: Incorporación y validación de comprobante** | [SPEC-003](../specs/003-matias-documentos.md), [SPEC-009](../specs/009-matias-integracion-compartida.md) | Contrato de validación por referencia `doc_id` | **Q4**: Formatos y tipos de comprobantes admisibles |

---

## 4. Estado de avance y próximos pasos

1. **Revisión técnica de interfaces:** Trasladar estas 4 decisiones como base de discusión con Matías para consensuar los contratos compartidos de S1, sin adelantar código ni migraciones.
2. **Preservación de límites:** No considerar este documento como habilitación para pasar a `Ready` ni para iniciar S3 (persistencia real).
3. **Independencia de I1:** Mantener el seguimiento de T06 y T07 en sus canales correspondientes (PR #14 / Issue #8 y Issue #9) sin darlas por concluidas.
