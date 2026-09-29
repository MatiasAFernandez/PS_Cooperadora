# Guía de Reproducción Local — Demostración Técnica I1

Esta guía describe el procedimiento para reproducir localmente y paso a paso el circuito técnico completo del incremento I1 utilizando las cuentas sintéticas preparadas.

---

## 1. Requisitos previos y entorno de ejecución

### 1.1. Contexto de ejecución y convenciones de comandos
- **Para Franco (ejecutando en su entorno local):**
  - **Raíz de trabajo:** Worktree `C:\dev\PS_Cooperadora_T03` o checkout principal `C:\dev\PS_Cooperadora`.
  - **Intérprete Python:** Usar la ruta absoluta del entorno virtual existente:
    `C:\dev\PS_Cooperadora\.venv\Scripts\python.exe`
  - **Configuración:** Verificar que el archivo `.env` del checkout donde se ejecute contenga `DEMO_IDENTITY_ENABLED=true`.
  - **Base de datos:** Reutilizar el contenedor Docker PostgreSQL existente (`ps-cooperadora-db-1`) sin reiniciar volúmenes ni reinstalar paquetes:
    ```powershell
    docker compose up -d --wait db
    ```
- **Para Matías (ejecutando en su entorno independiente):**
  - Ejecutar en su propio checkout local con su entorno virtual activo (conforme a `README.md` y `docs/guides/identidad-demo-local.md`).
  - Configurar en su `.env` local: `DEMO_IDENTITY_ENABLED=true`.
  - Usar su comando de entorno virtual activo (ej: `.\.venv\Scripts\python.exe` en Windows o `python` con venv activado).
  - Verificar base de datos PostgreSQL local activa y aplicar migraciones.

### 1.2. Aprovisionamiento de cuentas sintéticas
El comando de aprovisionamiento es idempotente y conserva las cuentas si ya existen:

- **Franco (PowerShell):**
  ```powershell
  C:\dev\PS_Cooperadora\.venv\Scripts\python.exe manage.py preparar_identidad_demo
  ```
- **Matías (con venv activo):**
  ```powershell
  python manage.py preparar_identidad_demo
  ```

Si es la primera inicialización en el entorno, establecer contraseñas interactivas privadas (conservadas exclusivamente en el gestor local de cada integrante):
- **Franco:**
  ```powershell
  C:\dev\PS_Cooperadora\.venv\Scripts\python.exe manage.py changepassword demo_a
  C:\dev\PS_Cooperadora\.venv\Scripts\python.exe manage.py changepassword demo_b
  C:\dev\PS_Cooperadora\.venv\Scripts\python.exe manage.py changepassword demo_o
  C:\dev\PS_Cooperadora\.venv\Scripts\python.exe manage.py changepassword demo_l
  ```
- **Matías:**
  ```powershell
  python manage.py changepassword demo_a
  python manage.py changepassword demo_b
  python manage.py changepassword demo_o
  python manage.py changepassword demo_l
  ```

### 1.3. Iniciar el servidor de desarrollo
- **Franco:**
  ```powershell
  C:\dev\PS_Cooperadora\.venv\Scripts\python.exe manage.py runserver
  ```
- **Matías:**
  ```powershell
  python manage.py runserver
  ```

---

## 2. Perfiles y cuentas sintéticas

| Usuario | Perfil / Rol | Capacidades en demo |
|---|---|---|
| `demo_a` | Solicitante A | `gastos.presentar`, `gastos.consultar_propias` |
| `demo_b` | Solicitante B | `gastos.presentar`, `gastos.consultar_propias` |
| `demo_o` | Operadora O | `gastos.consultar_todas`, `gastos.decidir` |
| `demo_l` | Cuenta Lectura L | `gastos.consultar_todas` |

---

## 3. Recorrido del Circuito Técnico (Escenarios 1 a 8)

> [!IMPORTANT]
> **Identificadores dinámicos y repetición del circuito:**
> La base de datos puede contener trámites preexistentes. Al presentar cada nuevo gasto, se debe registrar el identificador real asignado por el servidor en la URL `/gastos/<ID>/` (denominados `ID_A1` e `ID_A2`) y reutilizarlos en los pasos posteriores.
> Para una nueva corrida o repetición manual del circuito, siempre deben presentarse nuevos gastos, ya que los gastos de ejecuciones anteriores quedan en estados terminales (`Aceptada` o `Rechazada`).

---

### Escenario 1: Acceso de Solicitante A y presentación de Gasto 1 (`ID_A1`)
1. Abrir navegador e ingresar a `http://127.0.0.1:8000/demo/acceso/`.
2. Iniciar sesión con usuario `demo_a` y su contraseña local.
3. Navegar a `/gastos/presentar/`.
4. Completar el formulario:
   - **Concepto / Justificación:** `Insumos de laboratorio de prueba T06`
   - **Importe Estimado (ARS):** `45000.00`
   - **Unidad Requirente:** `Laboratorio de Química`
5. Presionar **Enviar Solicitud**.
6. **Verificación:**
   - Redirección HTTP 302 hacia `/gastos/<ID_A1>/` (anotar el ID asignado, ej: `5`, `8`, etc.).
   - El estado figura como **Presentada**, Versión **0**.
   - En *Documentación de Respaldo* se visualiza:
     > `No se solicita documentación en esta etapa de la demostración`
   - No se muestran paneles de decisión ni controles de carga de archivos.
7. Cerrar sesión mediante POST en `/demo/salida/` o en `/demo/`.

---

### Escenario 2: Postergación y Aceptación por Operadora O (`ID_A1`)
1. Iniciar sesión con usuario `demo_o` en `/demo/acceso/`.
2. Navegar directamente al detalle del gasto: `/gastos/<ID_A1>/`.
3. **Comprobación de UI:** Se visualiza el panel *Registrar Decisión Humana* con versión esperada `0` y tres acciones (Aceptar, Postergar, Rechazar).
4. **Postergación:**
   - Ingresar motivo: `Se requiere cotización formal adicional de insumos`
   - Presionar **Postergar**.
5. **Verificación post-postergación:**
   - Redirección HTTP 302 a `/gastos/<ID_A1>/`.
   - Estado: **Postergada**, Versión **1**.
   - En *Documentación de Respaldo* persiste:
     > `No se solicita documentación en esta etapa de la demostración`
   - En *Historial de Decisiones* figura 1 evento: autor `demo_o`, estado anterior `Presentada`, estado resultante `Postergada` y el motivo ingresado.
6. **Aceptación:**
   - En el panel de decisión (ahora con versión esperada `1`), ingresar motivo: `Cotización recibida y aprobada por Cooperadora`
   - Presionar **Aceptar**.
7. **Verificación post-aceptación:**
   - Redirección HTTP 302 a `/gastos/<ID_A1>/`.
   - Estado: **Aceptada**, Versión **2**.
   - En *Documentación de Respaldo* se visualiza exactamente:
     > **`Respaldo del gasto (presupuesto o factura): por aportar`**
   - El panel *Registrar Decisión Humana* **ya no se renderiza** (`Aceptada` es estado terminal en I1).
   - En *Historial de Decisiones* figuran 2 eventos cronológicos con sus motivos.
8. Cerrar sesión (`/demo/salida/`).

---

### Escenario 3: Verificación de Historial y Respaldo por Solicitante A
1. Iniciar sesión con usuario `demo_a` en `/demo/acceso/`.
2. Navegar a `/gastos/<ID_A1>/`.
3. **Verificación:**
   - Solicitante A comprueba que su solicitud figura **Aceptada**, Versión **2**.
   - En *Documentación de Respaldo* permanece el mensaje:
     > **`Respaldo del gasto (presupuesto o factura): por aportar`**
   - En *Historial de Decisiones* se visualizan los dos eventos registrados por `demo_o`.
4. **Recarga en navegador (F5):**
   - Recargar la página; se comprueba que el estado, el mensaje H4 y el historial persisten idénticos e invariables.
5. Mantener la sesión activa para el siguiente paso.

---

### Escenario 4: Presentación de Gasto 2 por A (`ID_A2`)
1. Con la sesión de `demo_a`, ir a `/gastos/presentar/`.
2. Completar:
   - **Concepto / Justificación:** `Mobiliario y equipamiento informático T06`
   - **Importe Estimado (ARS):** `85000.00`
   - **Unidad Requirente:** `Administración`
3. Presionar **Enviar Solicitud**.
4. **Verificación y registro de ID:**
   - Redirección HTTP 302 a `/gastos/<ID_A2>/` (anotar el ID asignado, ej: `6`, `9`, etc.).
   - Estado: **Presentada**, Versión **0**.
5. Cerrar sesión (`/demo/salida/`).

---

### Escenario 5: Rechazo de Gasto 2 por Operadora O (`ID_A2`)
1. Iniciar sesión con usuario `demo_o` en `/demo/acceso/`.
2. Navegar a `/gastos/<ID_A2>/`.
3. En el panel de decisión:
   - Ingresar motivo: `Gasto no contemplado en presupuesto de demostración`
   - Presionar **Rechazar**.
4. **Verificación:**
   - Redirección HTTP 302 a `/gastos/<ID_A2>/`.
   - Estado: **Rechazada**, Versión **1**.
   - En *Documentación de Respaldo* se visualiza:
     > `No se solicita documentación en esta etapa de la demostración`
   - Panel de decisión oculto (estado terminal).
   - Historial registra 1 evento con autor `demo_o`, motivo y transición a `Rechazada`.
5. Cerrar sesión (`/demo/salida/`).

---

### Escenario 6: Aislamiento de Solicitante B frente a los gastos de A
1. Iniciar sesión con usuario `demo_b` en `/demo/acceso/`.
2. Navegar a `/gastos/`.
3. **Verificación en listado:**
   - El Solicitante B **no visualiza ni `ID_A1` ni `ID_A2`** en su tabla de solicitudes (si no posee gastos propios previos, verá: *«No se encontraron solicitudes de gasto visibles para su cuenta»*).
4. **Intento de acceso directo por URL:**
   - Navegar a `http://127.0.0.1:8000/gastos/<ID_A1>/`
   - Navegar a `http://127.0.0.1:8000/gastos/<ID_A2>/`
5. **Verificación:**
   - En ambos casos el servidor responde **HTTP 404 Not Found**, preservando el aislamiento estricto sin filtrar metadatos ni confirmar la existencia del trámite ajeno.
6. Cerrar sesión (`/demo/salida/`).

---

### Escenario 7: Consulta de L y Denegación de Decisión con CSRF válido
1. Iniciar sesión con usuario `demo_l` en `/demo/acceso/`.
2. Navegar a `/gastos/`.
3. **Verificación de visibilidad global:**
   - Cuenta L visualiza tanto `ID_A1` como `ID_A2` en el listado (posee capacidad `gastos.consultar_todas`).
4. Navegar al detalle: `/gastos/<ID_A1>/`.
5. **Verificación en UI:**
   - Visualiza los datos y el historial completo.
   - **No se renderiza** el bloque *Registrar Decisión Humana* (no posee `gastos.decidir`).
6. **POST directo con sesión y token CSRF válido:**
   - Abrir la consola de desarrollo del navegador (F12) en `/gastos/<ID_A1>/` con la sesión de `demo_l` activa y ejecutar el siguiente fragmento JavaScript:
     ```javascript
     // Obtiene dinámicamente el ID del gasto a partir de la URL actual (/gastos/<ID>/)
     const idGasto = window.location.pathname.split('/').filter(Boolean)[1];
     const csrfToken = document.cookie.split('; ').find(r => r.startsWith('csrftoken='))?.split('=')[1];

     if (!csrfToken) {
       console.error('ERROR: No se encontró la cookie csrftoken.');
     } else {
       fetch(`/gastos/${idGasto}/decidir/`, {
         method: 'POST',
         headers: {
           'X-CSRFToken': csrfToken,
           'Content-Type': 'application/x-www-form-urlencoded',
         },
         body: 'action=aceptar&version=2&motivo=Intento+sin+permiso'
       }).then(async res => {
         const body = await res.text();
         console.log('HTTP Status recibido:', res.status);
         if (res.status === 403) {
           if (body.toLowerCase().includes('csrf')) {
             console.warn('RECHAZO CSRF: La petición fue interceptada por el middleware CSRF.');
           } else {
             console.log('HTTP 403 recibido con token CSRF válido (no es fallo de CSRF).');
             console.log('La denegación de negocio se corrobora en gastos.views/services y pruebas unitarias.');
           }
         }
       });
     }
     ```
7. **Verificación:**
   - Responde **HTTP 403 Forbidden**. Se comprueba que el token CSRF estaba presente en headers y cookie, y que la respuesta no corresponde a la página de fallo de CSRF.
   - La causa de negocio (`ExpensePermissionDeniedError: El actor no posee la capacidad 'gastos.decidir'`) está respaldada por la vista y las pruebas automatizadas.
   - La solicitud `ID_A1` en base de datos permanece en estado `Aceptada` y versión `2` sin escrituras adicionales (0 escrituras).
8. Cerrar sesión (`/demo/salida/`).

---

### Escenario 8: Creación sintética y prohibición de auto-decisión a Operadora O (H2)
1. **Creación sintética:**
   Dado que `demo_o` no posee la capacidad de presentar gastos según el contrato de demo, crear una solicitud de prueba asignada a `demo_o` desde la terminal:
   - **Franco (PowerShell):**
     ```powershell
     C:\dev\PS_Cooperadora\.venv\Scripts\python.exe manage.py shell -c "from django.contrib.auth import get_user_model; from gastos.models import SolicitudGasto; u = get_user_model().objects.get(username='demo_o'); s = SolicitudGasto.objects.create(concepto='Gasto sintético para prueba de auto-decisión H2 T06', monto_estimado=15000.00, unidad_requirente='Cooperadora', solicitante=u, estado='presentada', version=0); print(f'ID_O={s.pk}')"
     ```
   - **Matías (con venv activo):**
     ```powershell
     python manage.py shell -c "from django.contrib.auth import get_user_model; from gastos.models import SolicitudGasto; u = get_user_model().objects.get(username='demo_o'); s = SolicitudGasto.objects.create(concepto='Gasto sintético para prueba de auto-decisión H2 T06', monto_estimado=15000.00, unidad_requirente='Cooperadora', solicitante=u, estado='presentada', version=0); print(f'ID_O={s.pk}')"
     ```
   Tomar nota del ID devuelto (**`ID_O`**, ej: `7`, `10`, etc.).
2. Iniciar sesión con usuario `demo_o` en `/demo/acceso/`.
3. Navegar a `/gastos/<ID_O>/`.
4. **Verificación en UI:**
   - La pantalla muestra el trámite en estado `Presentada`.
   - El panel *Registrar Decisión Humana* **no se renderiza** (`can_decide` evalúa `False` por regla H2: `solicitante_id == actor.subject_id`).
5. **POST directo con sesión y CSRF válidos:**
   - Abrir la consola de desarrollo del navegador (F12) en `/gastos/<ID_O>/` con la sesión de `demo_o` activa y ejecutar:
     ```javascript
     const idGastoPropio = window.location.pathname.split('/').filter(Boolean)[1];
     const csrfToken = document.cookie.split('; ').find(r => r.startsWith('csrftoken='))?.split('=')[1];

     if (!csrfToken) {
       console.error('ERROR: No se encontró la cookie csrftoken.');
     } else {
       fetch(`/gastos/${idGastoPropio}/decidir/`, {
         method: 'POST',
         headers: {
           'X-CSRFToken': csrfToken,
           'Content-Type': 'application/x-www-form-urlencoded',
         },
         body: 'action=aceptar&version=0&motivo=Auto+aprobacion'
       }).then(async res => {
         const body = await res.text();
         console.log('HTTP Status recibido:', res.status);
         if (res.status === 403) {
           if (body.toLowerCase().includes('csrf')) {
             console.warn('RECHAZO CSRF: La petición fue interceptada por el middleware CSRF.');
           } else {
             console.log('HTTP 403 recibido con token CSRF válido (no es fallo de CSRF).');
             console.log('La denegación de auto-decisión H2 se corrobora en can_decide_expense/decide_expense y pruebas.');
           }
         }
       });
     }
     ```
6. **Verificación:**
   - Responde **HTTP 403 Forbidden**. Se comprueba token CSRF válido y ausencia de la página de error CSRF.
   - La causa de negocio (regla H2: `solicitante_id == actor.subject_id`) está respaldada por la vista y las pruebas.
   - La solicitud `ID_O` en base de datos permanece en estado `Presentada`, versión `0` y sin decisiones registradas en el historial (0 escrituras).
7. Cerrar sesión (`/demo/salida/`).
