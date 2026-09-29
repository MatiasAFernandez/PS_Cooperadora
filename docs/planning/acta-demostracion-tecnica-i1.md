# Acta Técnica de Demostración — Incremento I1 (T06 / Issue #8)

## 1. Identificación y Participantes

- **Fecha de elaboración del acta:** 28/09/2026.
- **Participantes:**
  - Franco Damián Sánchez (`@FranDSchz`) — Responsable de integración de gastos, decisiones, historial y documentación pendiente.
  - Matías Alejandro Fernández (`@MatiasAFernandez`) — Responsable de identidad sintética y reproducción independiente.
- **Versión de software evaluada:** Base integrada en `main` commit [`bbcf1c84`](https://github.com/MatiasAFernandez/PS_Cooperadora/commit/bbcf1c84bd4cb4ecb1fb7223ade3781e22dfc27d).
- **Entorno técnico de ejecución:**
  - **Entorno de Franco:**
    - Checkout principal `C:\dev\PS_Cooperadora` y worktree de trabajo `C:\dev\PS_Cooperadora_T03`.
    - Sistema Operativo: Windows 11 / PowerShell.
    - Intérprete: Python 3.11.9 (64-bit), Django 5.2.17 (ejecutado con la ruta absoluta `C:\dev\PS_Cooperadora\.venv\Scripts\python.exe`).
    - Base de Datos: PostgreSQL 17.11 en contenedor Docker (`ps-cooperadora-db-1`), puerto 5432.
    - Configuración: `DEMO_IDENTITY_ENABLED=true` en `.env`.
  - **Entorno de Matías:**
    - Entorno local independiente conforme a `README.md` y `docs/guides/identidad-demo-local.md`, con `DEMO_IDENTITY_ENABLED=true`.

---

## 2. Registro de Pruebas Automatizadas y de Integración

### 2.1. Línea base verificada en `main` (commit `bbcf1c84`)
- **CI Remoto (GitHub Actions):** [Run 36370624415](https://github.com/MatiasAFernandez/PS_Cooperadora/actions/runs/36370624415) completado con estado **SUCCESS** (107 pruebas aprobadas en 3.49 s contra PostgreSQL).
- **Ejecución local previa de control:** 107 pruebas aprobadas en 12.39 s (registrada en `task-72.log`).

### 2.2. Verificaciones específicas ejecutadas para T06

| Control | Comando | Resultado Franco | Resultado Matías |
|---|---|---|---|
| Linter y formato | `C:\dev\PS_Cooperadora\.venv\Scripts\python.exe -m ruff check .` | Aprobado (All checks passed, 0 errores) | [Pendiente Matías] |
| Chequeo de sistema Django | `C:\dev\PS_Cooperadora\.venv\Scripts\python.exe manage.py check` | Aprobado (0 issues silenced) | [Pendiente Matías] |
| Consistencia de migraciones | `C:\dev\PS_Cooperadora\.venv\Scripts\python.exe manage.py makemigrations --check --dry-run` | Aprobado (No changes detected) | [Pendiente Matías] |
| Espacios y formato Git | `git diff --check` *(archivos seguidos e inspección explícita de nuevos)* | Aprobado (código 0, limpio) | [Pendiente Matías] |
| Suite completa contra PostgreSQL | `C:\dev\PS_Cooperadora\.venv\Scripts\python.exe -m pytest -q` | **107 passed in 11.48s** (task-119) | [Pendiente de recepción] |

### 2.3. Ejecución automatizada complementaria del recorrido completo (Escenarios 1 a 8)
- **Método:** Ejecución programática mediante script (`verificar_recorrido_t06.py`) utilizando `django.test.Client(enforce_csrf_checks=True)` con sesiones reales de las cuatro cuentas contra la base PostgreSQL de desarrollo (`ps-cooperadora-db-1`).
- **Identificadores dinámicos registrados:** `ID_A1 = 5`, `ID_A2 = 6`, `ID_O = 7`.
- **Resultado:** Los 8 escenarios resultaron plenamente aprobados sin errores HTTP 500 no controlados, verificando la persistencia exacta de estados, versiones e historial, y confirmando que los POST de L y O fueron evaluados y denegados por la capa de negocio (`ExpensePermissionDeniedError` y regla H2) con 0 escrituras en base de datos.
- **Nota de repetición:** Dado que los gastos `ID_A1=5` e `ID_A2=6` quedaron en estados terminales (`Aceptada` y `Rechazada`), toda repetición del circuito requerirá la presentación de nuevos gastos.

---

## 3. Matriz de Resultados del Recorrido Manual en Navegador

*(Para la verificación interactiva en navegador se requerirá generar nuevos identificadores dinámicos, ya que 5 y 6 quedaron en estados terminales).*

| Escenario | Actor | Acción prevista | Resultado esperado | Resultado manual en navegador (Franco) | Resultado manual en navegador (Matías) |
|---|---|---|---|---|---|
| **1. Presentación G1** | `demo_a` | Alta de gasto por $45.000 (Lab Química) vía `/gastos/presentar/` | HTTP 302 hacia `/gastos/<ID_A1>/`. Detalle en estado `Presentada`, v=0, mensaje: «*No se solicita documentación en esta etapa de la demostración*». Historial vacío. | [Pendiente de ejecución manual interactiva en navegador por Franco] | [Pendiente de recepción de resultados independientes] |
| **2. Postergación y Aceptación G1** | `demo_o` | Postergación con motivo sobre `ID_A1`, luego aceptación con motivo | Postergación: 302 -> Detalle v=1, `Postergada`, mensaje H4 alternativo. Aceptación: 302 -> Detalle v=2, `Aceptada`, mensaje: «*Respaldo del gasto (presupuesto o factura): por aportar*». Panel de decisión oculto. | [Pendiente de ejecución manual interactiva en navegador por Franco] | [Pendiente de recepción de resultados independientes] |
| **3. Consulta Aceptada G1** | `demo_a` | Reingreso a `/gastos/<ID_A1>/` y recarga (F5) | Visualiza estado `Aceptada`, v=2, mensaje H4 «*por aportar*» y 2 eventos en historial. Recarga conserva datos e HTML idénticos. | [Pendiente de ejecución manual interactiva en navegador por Franco] | [Pendiente de recepción de resultados independientes] |
| **4. Presentación G2** | `demo_a` | Alta de segundo gasto por $85.000 (Administración) | HTTP 302 hacia `/gastos/<ID_A2>/`. Detalle en estado `Presentada`, v=0. | [Pendiente de ejecución manual interactiva en navegador por Franco] | [Pendiente de recepción de resultados independientes] |
| **5. Rechazo G2** | `demo_o` | Rechazo con motivo sobre `ID_A2` | HTTP 302 hacia `/gastos/<ID_A2>/`. Estado `Rechazada`, v=1, mensaje H4 alternativo. Panel de decisión oculto. Historial registra 1 evento. | [Pendiente de ejecución manual interactiva en navegador por Franco] | [Pendiente de recepción de resultados independientes] |
| **6. Aislamiento B** | `demo_b` | Consulta de listado `/gastos/` e intento de acceso directo por URL a `ID_A1` e `ID_A2` | Listado no muestra `ID_A1` ni `ID_A2`. GET a `/gastos/<ID_A1>/` y `/gastos/<ID_A2>/` responde HTTP 404 estricto (no revela existencia). | [Pendiente de ejecución manual interactiva en navegador por Franco] | [Pendiente de recepción de resultados independientes] |
| **7. Denegación L con CSRF** | `demo_l` | Consulta global y POST directo con sesión y token CSRF válido a `/gastos/<ID_A1>/decidir/` | Listado visualiza `ID_A1` e `ID_A2`. Detalle no renderiza formulario de decisión. POST directo con CSRF responde HTTP 403 Forbidden. BD inalterada. | [Pendiente de ejecución manual interactiva en navegador por Franco] | [Pendiente de recepción de resultados independientes] |
| **8. Auto-decisión O (H2)** | `demo_o` | Creación sintética de `ID_O` (solicitante `demo_o`) y POST directo con sesión y token CSRF válido | Detalle no renderiza formulario de decisión (`can_decide=False`). POST directo responde HTTP 403 Forbidden por regla H2. BD inalterada. | [Pendiente de ejecución manual interactiva en navegador por Franco] | [Pendiente de recepción de resultados independientes] |

---

## 4. Comprobaciones de Errores y Excepciones

- **Errores no controlados:** Se constató la **ausencia total de errores HTTP 500** en todos los flujos efectivamente probados (automatizados e integración complementaria).
- **Validación de formulario y Bad Request (HTTP 400):**
  - Verificado en automatización: Rechazo de omisión de motivo obligatorio en postergar y rechazar, versiones no numéricas, flotantes, caracteres no ASCII (B3) y bytes NUL (B4) en `test_decisiones_views.py` y `test_decisiones_services.py`.
  - Verificación manual en UI (re-renderizado del formulario con mensaje de error): Pendiente de registrar junto con el recorrido interactivo en navegador.
- **Métodos no permitidos (HTTP 405):**
  - Verificado en automatización (`test_security_csrf.py`): Peticiones GET dirigidas al endpoint de decisión responden HTTP 405 Method Not Allowed sin producir efectos.
- **Conflictos de concurrencia y transiciones inválidas (HTTP 409):**
  - Verificado en automatización (`test_concurrency.py`): Decisiones concurrentes sobre la misma versión producen exactamente una aceptación y un HTTP 409 Conflict.
  - Transiciones no permitidas desde estados terminales (`aceptada` o `rechazada`) responden HTTP 409 sin registrar nuevos eventos.
- **Reversión atómica de transacciones:**
  - Verificado en automatización: Fallos provocados al persistir eventos de auditoría revierten íntegramente estado, versión y registros históricos (`@transaction.atomic`).
- **Distinción entre CSRF y denegación de negocio:**
  - En los escenarios 7 y 8, la verificación programática comprobó que las peticiones POST enviaron el token CSRF válido (`HTTP_X_CSRFTOKEN` y `csrfmiddlewaretoken`) y que la respuesta HTTP 403 no correspondió a la página de fallo de CSRF.
  - La causa de negocio (`ExpensePermissionDeniedError` y regla H2) está corroborada por la lógica de vistas/servicios y la suite de pruebas automatizadas, confirmando 0 escrituras en base de datos.

---

## 5. Limitaciones Técnicas y Alcance No Cubierto

1. **Adaptador de demostración:**
   El circuito depende de la activación explícita de `DEMO_IDENTITY_ENABLED=true` y del uso de cuentas sintéticas locales (`demo_a`, `demo_b`, `demo_o`, `demo_l`). No sustituye ni preconfigura el sistema de identidad institucional definitivo de la Facultad.
2. **Sin circuito de pagos:**
   La acción «Aceptar» constituye exclusivamente una resolución interna de demostración; no acredita pago, no realiza reservas contables ni emite comprobantes de transferencia.
3. **Sin carga ni validación de archivos:**
   No existe soporte para adjuntar archivos PDF o imágenes ni para marcar conformidad documental.
4. **Mensaje de respaldo provisional (H4):**
   El texto «*Respaldo del gasto (presupuesto o factura): por aportar*» representa una guía visual de demostración para el usuario solicitante; no certifica recepción ni reemplaza una factura definitiva posterior al pago.

---

## 6. Puntos Clave para la Validación Operativa con Cooperadora (T07 / Issue #9)

A partir de los resultados técnicos obtenidos, se identifican los siguientes puntos para someter a consideración de la operadora en la sesión de validación:
1. **Campos mínimos de presentación (H1):**
   Confirmar si el concepto, importe estimado y unidad requirente resultan suficientes o si en la práctica institucional se requieren desgloses, rangos de importes o centros de costo específicos.
2. **Autoridad y delegaciones en Cooperadora (H2/H3):**
   Definir formalmente qué personas u operadores tienen la potestad de postergar, rechazar y aceptar gastos, y si existen umbrales de monto que requieran más de un revisor.
3. **Tratamiento de gastos propios de operadores (H2):**
   Validar si la prohibición estricta de auto-decisión probada en la demo se condice con la política real de Cooperadora o si se requiere un mecanismo formal de delegación cuando un operador presenta una necesidad propia.
4. **Requisitos documentales y momento de exigibilidad (H4):**
   Determinar qué comprobante específico (presupuesto previo, proforma o factura comercial) se exige para habilitar un pago, distinguiéndolo de la rendición o comprobante posterior a la transferencia bancaria.

---

## 7. Conformidad Técnica Acordada

- **Franco Damián Sánchez (`@FranDSchz`):**
  - Conformidad técnica registrada el 28/09/2026 respecto de la suite automatizada completa (107/107 pruebas) y de la ejecución complementaria de los 8 escenarios. Recorrido manual en navegador pendiente de registrar con nuevos IDs.
- **Matías Alejandro Fernández (`@MatiasAFernandez`):**
  - *Pendiente de recepción de resultados independientes y registro de conformidad técnica.*
