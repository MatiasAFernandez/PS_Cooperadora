# Paquete de Auditoría Técnica — Issue #91 (Incremento I3)

**Destinatario:** Gemini Argon (Auditor Técnico Senior)  
**Rama:** `feat/91-retencion-atp-pagos`  
**Fecha:** 2026-11-03  
**Estado:** Listo para revisión y merge  

---

## 1. Alcance y Objetivos

El presente paquete documenta la implementación completa de la **Issue #91 (`I3-03`)**: `feat(gastos): parametrización y cálculo de retención ATP con CheckConstraint SQL y firma compatible`, conjuntamente con la resolución previa de los **3 ajustes de borde de la Issue #90** solicitados por la auditoría técnica.

---

## 2. Ajustes de Borde de Issue #90 (Incorporados)

1. **Filtrado del selector documental por flujo (`gastos/views.py`):**
   - En `_listar_opciones_documentales(proveedor, actor, solicitud)` se pasa explícitamente `tipos_admitidos=tipos_documento_admitidos_para_flujo(getattr(solicitud, "tipo_flujo", None))` y se filtra de forma estricta.
   - En solicitudes con `tipo_flujo == "REINTEGRO"`, `GET /gastos/<pk>/pagar/` no ofrece opciones de tipo `presupuesto` o `proforma` en el selector del formulario web (sólo `factura`).
   - Verificado con test de vista dedicado: `test_view_pagar_reintegro_no_lista_presupuesto` en `tests/gastos/test_doble_flujo.py`.

2. **Prevención de colisión de `centro_costo` en POST web (`SolicitudGastoCreateView`):**
   - Se segregan `cc_catalog_raw` y `cc_transfer_raw` examinando `request.POST.getlist("centro_costo")`.
   - Si el valor único enviado corresponde a una selección de catálogo o ID numérico, se inyecta de forma limpia y transparente `cc.nombre` en `datos_post["centro_costo"]` (y nunca la PK numérica `"1"`). Si el valor es textual libre, se respeta como imputación operativa de la transferencia sin desbordar el ORM ni causar `ValueError: invalid literal for int()`.
   - Verificado con test de integración: `test_view_presentar_solicitud_con_datos_transferencia_sincroniza_nombre_centro` en `tests/gastos/test_doble_flujo.py`.

3. **Guardia ante diccionario de transferencia vacío en `crear_solicitud_gasto` (`gastos/services.py`):**
   - La sincronización automática de `datos_transferencia["centro_costo"]` se condiciona estrictamente a que al menos uno de los otros 4 campos bancarios (`titular_nombre`, `identificacion`, `cbu_alias`, `correo_comprobante`) contenga datos reales no vacíos.
   - Evita la excepción espuria `DatosTransferenciaInvalidInputError` cuando se invoca la creación con un diccionario de 5 claves en blanco.
   - Verificado con test: `test_crear_solicitud_gasto_con_datos_transferencia_vacios_no_falla` en `tests/gastos/test_doble_flujo.py`.

---

## 3. Implementación de Issue #91

### 3.1 Modelo `PagoExterno` y Restricción SQL (`gastos/models.py`)
- Agregados los campos contables impositivos:
  - `monto_bruto = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"), validators=[MinValueValidator(Decimal("0.01"))])`
  - `monto_retencion_atp = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))`
  - `referencia_atp = models.CharField(max_length=128, blank=True, default="")`
- `CheckConstraint` SQL en `PagoExterno.Meta.constraints`:
  ```python
  models.CheckConstraint(
      condition=Q(importe=models.F("monto_bruto") - models.F("monto_retencion_atp"))
      & Q(monto_retencion_atp__gte=Decimal("0.00"))
      & Q(monto_bruto__gt=Decimal("0.00")),
      name="pago_externo_identidad_neto_atp",
  )
  ```
- Inicializador `__init__` y método `clean()` configurados para garantizar que llamadas directas de modelos preexistentes adopten `monto_bruto = importe` de forma determinista y consistente.

### 3.2 Migración Estructural Limpia (`gastos/migrations/0010_...`)
- Migración `0010_pagoexterno_monto_bruto_and_more.py` estrictamente estructural.
- Incluye un `RunSQL("UPDATE gastos_pagoexterno SET monto_bruto = importe WHERE monto_bruto = 0;", reverse_sql=RunSQL.noop)` seguro entre la adición de campos y la creación del `CheckConstraint`, garantizando que filas preexistentes satisfagan la identidad contable sin insertar registros en tablas de trámites/usuarios (100% compatible con `muestra_entrega`).

### 3.3 Retrocompatibilidad Estricta en Servicios (`gastos/payments.py`)
- `registrar_pago_externo` incorpora parámetros opcionales con defaults neutros:
  `monto_bruto: Any = None, monto_retencion_atp: Any = Decimal("0.00"), referencia_atp: Any = ""`
- **Regla de fallback neutro:** si `monto_bruto is None` y la retención es nula, asume `monto_bruto = valid_importe`.
- **Validación decimal estricta (`_validar_decimal_estricto` y `validate_retencion_atp_input`):** rechaza floats, bools, números no finitos y sobreprecisión (>2 decimales). Exige `monto_retencion_atp >= 0.00`, `monto_bruto > 0.00` y verifica rigurosamente $\text{Importe Neto} = \text{Monto Bruto} - \text{Monto Retención ATP}$, emitiendo `PaymentInvalidInputError` (HTTP 400) ante cualquier inconsistencia.
- **Huella canónica de idempotencia (`calcular_huella_pago`):** cuando no hay retención, el payload JSON conserva exactamente las 6 claves históricas sin alterar los hashes ni la verificación determinista de `muestra_entrega`.
- **Detección de conflictos:** si se reenvía un pago contra una solicitud que ya cuenta con un pago persistido y difieren los datos de retención (`monto_bruto`, `monto_retencion_atp` o `referencia_atp`), se emite `PaymentConflictError` (HTTP 409).
- **Consulta DTO (`PagoExternoConsulta`):** expone de forma pura `monto_bruto`, `monto_retencion_atp` y `referencia_atp` sin filtrar metadatos sensibles ni requerir provider documental.

### 3.4 Interfaz de Usuario y Tokens Institucionales
- **Formulario (`gastos/forms.py`):** `PagoExternoForm` incorpora campos opcionales para `monto_bruto`, `monto_retencion_atp` y `referencia_atp`.
- **Vista (`gastos/views.py`):** `SolicitudGastoPagoView` inyecta al contexto `base_imponible_atp`, `alicuota_atp`, bandera `aplica_atp` y el cálculo sugerido `monto_retencion_sugerido`.
- **Plantilla de Pago (`templates/gastos/pago_form.html`):** si `solicitud.monto_estimado >= base_imponible_atp`, despliega el banner de advertencia preventiva (`.message.message-warning` de tokens UTN) con el porcentaje sugerido (3,5%) e importe sugerido, y ofrece el bloque de campos para que el operador verifique y confirme la retención.
- **Detalle de Solicitud (`templates/gastos/solicitud_detail.html`):** cuando el pago tiene retención (`monto_retencion_atp > 0`), exhibe el desglose contable claro: Monto Bruto, Retención ATP Chaco (con chip de certificado) e Importe Neto Transferido.

---

## 4. Matriz de Pruebas

Se creó la suite dedicada [`tests/gastos/test_retencion_atp.py`](file:///home/fran/repos/PS_Cooperadora/tests/gastos/test_retencion_atp.py):

| Prueba | Componente | Verificación |
|---|---|---|
| `test_calculo_sugerido_parametros_default_y_personalizados` | Parámetros BD / Fallback | Fallback $90.000 / 3,5% y sobreescritura desde `ParametroOperativo` |
| `test_validate_retencion_atp_input_casos` | Validador puro | Identidad contable, rechazo de retención sin bruto, retención negativa |
| `test_pago_sin_retencion_retrocompatible` | `registrar_pago_externo` | Fallback neutro `monto_bruto = importe`, retención 0.00, reenvío idéntico |
| `test_pago_con_retencion_valida_y_consulta` | Servicio y DTO | Registro atómico y consulta de bruto, retención y referencia ATP |
| `test_conflicto_idempotencia_si_cambian_datos_retencion` | Idempotencia C03 | Disparo de `PaymentConflictError` (HTTP 409) ante cambio en retención |
| `test_check_constraint_db_identidad_neto_atp` | PostgreSQL / SQL | Violación directa del CheckConstraint a nivel motor (`IntegrityError`) |
| `test_vista_pago_muestra_aviso_y_calculo_sugerido_atp` | Vista GET | Aviso preventivo, tokens institucionales y cálculo sugerido en UI |
| `test_vista_pago_post_con_retencion_y_desglose_en_detalle` | Vista POST / Detalle | Registro web con retención y renderizado del desglose en `solicitud_detail` |

---

## 5. Resultados de Verificación de Integridad

### 5.1 Django System Check
```bash
$ python manage.py check
System check identified no issues (0 silenced).
```

### 5.2 Linter y Formato
```bash
$ ruff check .
All checks passed!
```

### 5.3 Verificación de Migraciones
```bash
$ python manage.py makemigrations --check
No changes detected
```

### 5.4 Suite Completa de Pruebas (Pytest)
```bash
$ python -m pytest -q
........................................................................ [  9%]
........................................................................ [ 19%]
........................................................................ [ 28%]
........................................................................ [ 38%]
........................................................................ [ 48%]
........................................................................ [ 57%]
........................................................................ [ 67%]
........................................................................ [ 76%]
........................................................................ [ 86%]
........................................................................ [ 96%]
..............................                                           [100%]
750 passed in 133.26s (0:02:13)
```

### 5.5 Comando de Recuperación y Entrega
```bash
$ pytest tests/integracion/test_muestra_entrega.py
tests/integracion/test_muestra_entrega.py ...                            [100%]
3 passed in 2.53s
```
Huellas de `muestra_entrega crear` y `muestra_entrega verificar` 100% conservadas y reproducibles.
