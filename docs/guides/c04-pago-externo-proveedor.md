# Guía de reproducción técnica C04 (#49 / #50): Pago externo con proveedor documental

Esta guía detalla el procedimiento para reproducir en un entorno local
aislado (PostgreSQL I2) la integración C04 entre el circuito de gastos y el proveedor
documental real (`documentos.c01.ProveedorDocumentalGastos`), correspondiente a la
Issue #49 y la preparación de evidencia para #50. PR #62 integró DOC-R04 en main.
La proyección del historial por versión dentro del detalle del gasto se implementó en la
rama local `feat/49-revision-documental-gastos` (commit `be16bb6`). El 20/10/2026, una
corrida focalizada de 52 pruebas aprobó con PostgreSQL 17.11 aislado; no es la suite
completa ni el recorrido manual de #50. La rama aún no está integrada y la integración
conjunta de ambos circuitos sigue en #28. Para resultados anteriores y el estado de esa
verificación, véase la nota de la §4 y
[`docs/evidence/i2-49-revision-gastos.md`](../evidence/i2-49-revision-gastos.md).

> [!IMPORTANT]
> **Alcance y límites de la demostración técnica**:
> - Esta entrega aporta evidencia parcial a los criterios GP-01–GP-06 y no completa la totalidad de los criterios de SPEC-011. DOC-R04 está integrado mediante PR #62; Q1–Q5 siguen pendientes de validación institucional y GP-06 mantiene límites de cobertura de localización del trámite.
> - El tipo documental derivado en la vista de detalle es exclusivamente una categoría factual
>   de presentación (`factura`, `presupuesto` o degradación neutra `None`).
> - Un estado de revisión desconocido permite el recorrido técnico de la demo, pero **no equivale
>   a aprobación documental** ni acredita por sí solo el cumplimiento de una factura definitiva pendiente.
> - DOC-R04 está implementado en la aplicación; las decisiones institucionales Q1–Q5
>   (en particular Q4 sobre criterios definitivos de comprobantes válidos) permanecen
>   **pendientes de validación** con la institución.
> - Se mantienen estrictamente desacoplados: el hecho del pago (`PagoExterno`), el estado de la
>   solicitud de gasto (`SolicitudGasto.estado`, que conserva su estado `aceptada`) y la revisión documental.
> - No se implementa ejecución bancaria, pagos parciales, retenciones ni cierre de trámites.

---

## 1. Prerequisitos del entorno aislado

- **Sistema operativo**: Windows con PowerShell 7 / Windows PowerShell.
- **Python**: 3.11 o superior con entorno virtual activo.
- **PostgreSQL**: Instancia aislada 17 (alineada con la imagen fijada `postgres:17-alpine`) en contenedor Docker o servicio local en puerto no productivo.
- **Datos y credenciales**: Utilizar exclusivamente datos sintéticos de prueba. No almacenar contraseñas en scripts ni archivos, no versionar ni editar archivos `.env`, y no exponer credenciales en pantalla ni en el historial de comandos (la configuración del proyecto puede cargar variables de `.env`, pero las variables explícitas del proceso tienen precedencia).

---

## 2. Puesta en marcha o reutilización de PostgreSQL aislado con Docker

Para no colisionar con una instancia existente de I2, se debe verificar primero si el contenedor del servicio de base de datos ya existe en el host o si se debe desplegar una instancia nueva.

### 2.1. Descubrimiento y reutilización dinámica de la instancia existente

En este entorno, una inspección directa confirmó que la instancia existente de I2 cuenta con las etiquetas de Compose de proyecto `ps-cooperadora-i2-c04` y servicio `db`, base de datos y usuario `cooperadora_i2_c04`, y enlace configurado a loopback en `127.0.0.1:55432` (estando detenida al momento de ser inspeccionada).

En el siguiente bloque, las etiquetas de Compose de proyecto y servicio esperadas están fijadas para el descubrimiento; el nombre del contenedor, la base de datos, el usuario y el puerto publicado se derivan dinámicamente:
- Descubre el contenedor candidato mediante filtros exactos por etiquetas de Compose (`com.docker.compose.project=ps-cooperadora-i2-c04` y `com.docker.compose.service=db`), no por subcadena de nombre, verificando `$LASTEXITCODE` inmediatamente tras la consulta para no interpretar errores de Docker como ausencia de candidatos.
- Exige exactamente un candidato para ejecutar la reutilización. Si no existe ninguno, omite de forma segura las operaciones de reutilización y permite continuar a la sección 2.2 si se corre el bloque completo. Si existen múltiples candidatos o falla Docker, la ejecución se detiene con error.
- Inspecciona el candidato en memoria (validando `$LASTEXITCODE`), valida que posea las etiquetas exactas y una imagen de la familia PostgreSQL 17 (`postgres:17`, `postgres:17-*` o `postgres:17.*`), deriva su nombre y lo inicia si estuviera detenido (validando `$LASTEXITCODE` tras `docker start`), sin imprimir el JSON completo ni volcar variables de entorno.
- Deriva `POSTGRES_DB` y `POSTGRES_USER` directamente de la configuración en memoria del contenedor seleccionado, validando que exista exactamente un valor configurado para cada uno.
- Una vez en ejecución, deriva el puerto publicado mediante `docker port <nombre> 5432/tcp` (validando `$LASTEXITCODE`) y acepta única y exclusivamente un mapeo hacia loopback en formato `127.0.0.1:<puerto>`, fallando de forma segura (*fail-closed*) ante cualquier otra configuración.
- Solicita de forma interactiva y segura la contraseña de esa instancia, reteniéndola únicamente en el entorno del proceso de PowerShell sin exponer literales ni volcar variables.
- Ejecuta un bucle acotado de comprobación de disponibilidad del servidor (*server readiness*) mediante `pg_isready` (la verificación de credenciales a nivel de aplicación la realiza la suite de integración de Django).

```powershell
# 1. Descubrir el contenedor candidato por etiquetas exactas de Compose (no por subcadena de nombre)
$candidateIds = @(docker ps -a -q `
    --filter "label=com.docker.compose.project=ps-cooperadora-i2-c04" `
    --filter "label=com.docker.compose.service=db")

if ($LASTEXITCODE -ne 0) {
    throw "ERROR: Falló el comando 'docker ps' (código de salida $LASTEXITCODE). Verifique que Docker esté en ejecución y accesible."
}

if ($candidateIds.Count -gt 1) {
    throw "ERROR: Se detectaron múltiples contenedores candidatos ($($candidateIds.Count)) con las etiquetas de I2. Deteniendo la ejecución para evitar ambigüedades."
}

if ($candidateIds.Count -eq 0) {
    Write-Host "No se encontró ningún contenedor con las etiquetas exactas de I2. Omitiendo la reutilización; continúe en la sección 2.2 para desplegar una nueva instancia."
} elseif ($candidateIds.Count -eq 1) {
    $targetContainerId = $candidateIds[0]

    # 2. Inspeccionar el contenedor en memoria sin volcar JSON completo ni variables de entorno
    $rawInspect = docker inspect $targetContainerId
    if ($LASTEXITCODE -ne 0) {
        throw "ERROR: Falló el comando 'docker inspect' para el contenedor '$targetContainerId' (código de salida $LASTEXITCODE)."
    }
    $inspectData = $rawInspect | ConvertFrom-Json
    $containerInfo = $inspectData[0]

    # Validar etiquetas exactas e imagen de PostgreSQL 17
    $projLabel = $containerInfo.Config.Labels.'com.docker.compose.project'
    $servLabel = $containerInfo.Config.Labels.'com.docker.compose.service'
    $imageName = $containerInfo.Config.Image

    if ($projLabel -ne "ps-cooperadora-i2-c04" -or $servLabel -ne "db") {
        throw "ERROR: Las etiquetas del contenedor no coinciden exactamente con proyecto 'ps-cooperadora-i2-c04' y servicio 'db'."
    }
    if ($imageName -notmatch '^postgres:17($|[-.].*)') {
        throw "ERROR: La imagen del contenedor ('$imageName') no corresponde a PostgreSQL 17 (se esperaba 'postgres:17', 'postgres:17-*' o 'postgres:17.*')."
    }

    # Derivar el nombre del contenedor
    $containerName = $containerInfo.Name.TrimStart('/')

    # Iniciar el contenedor si está detenido
    if (-not $containerInfo.State.Running) {
        Write-Host "Iniciando contenedor '$containerName'..."
        docker start $containerName | Out-Null
        if ($LASTEXITCODE -ne 0) {
            throw "ERROR: Falló el comando 'docker start' para '$containerName' (código de salida $LASTEXITCODE)."
        }
    }

    # 3. Derivar POSTGRES_DB y POSTGRES_USER desde la configuración en memoria, validando un único valor de cada uno
    $envList = $containerInfo.Config.Env
    $dbValues = @($envList | Where-Object { $_ -like "POSTGRES_DB=*" } | ForEach-Object { $_.Substring(12) })
    $userValues = @($envList | Where-Object { $_ -like "POSTGRES_USER=*" } | ForEach-Object { $_.Substring(14) })

    if ($dbValues.Count -ne 1 -or [string]::IsNullOrWhiteSpace($dbValues[0])) {
        throw "ERROR: Se esperaba exactamente un valor para POSTGRES_DB en la configuración del contenedor."
    }
    if ($userValues.Count -ne 1 -or [string]::IsNullOrWhiteSpace($userValues[0])) {
        throw "ERROR: Se esperaba exactamente un valor para POSTGRES_USER en la configuración del contenedor."
    }

    $C04_PG_DB = $dbValues[0]
    $C04_PG_USER = $userValues[0]

    # 4. Derivar el puerto publicado y validar enlace exclusivo a loopback 127.0.0.1:<puerto> (fail-closed)
    $portLines = @(docker port $containerName 5432/tcp)
    if ($LASTEXITCODE -ne 0) {
        throw "ERROR: Falló el comando 'docker port' para '$containerName' (código de salida $LASTEXITCODE)."
    }
    if ($portLines.Count -ne 1) {
        throw "ERROR: Se esperaba exactamente un mapeo para 5432/tcp, pero se detectaron $($portLines.Count). Fallando de forma segura."
    }

    if ($portLines[0] -match '^127\.0\.0\.1:(\d+)$') {
        $C04_PG_PORT = $Matches[1]
    } else {
        throw "ERROR: El mapeo publicado '$($portLines[0])' no corresponde a una interfaz loopback 127.0.0.1:<puerto>. Fallando de forma segura."
    }

    # 5. Solicitar de forma interactiva y segura la contraseña para esta instancia
    # Se mantiene únicamente en el entorno del proceso PowerShell actual, sin literales ni exposición en consola
    $securePass = Read-Host "Ingrese la contraseña para PostgreSQL ($containerName)" -AsSecureString
    $env:POSTGRES_PASSWORD = [System.Net.NetworkCredential]::new("", $securePass).Password

    # 6. Bucle acotado de disponibilidad del servidor (server readiness)
    # pg_isready valida únicamente la disponibilidad del servidor a nivel de red;
    # la suite de integración de Django verificará las credenciales a nivel de aplicación.
    $maxAttempts = 15
    $attempt = 0
    $serverReady = $false
    while ($attempt -lt $maxAttempts) {
        $attempt++
        docker exec $containerName pg_isready -U $C04_PG_USER -d $C04_PG_DB | Out-Null
        if ($LASTEXITCODE -eq 0) {
            $serverReady = $true
            Write-Host "Servidor PostgreSQL listo para aceptar conexiones (intento $attempt)."
            break
        }
        Start-Sleep -Seconds 1
    }
    if (-not $serverReady) {
        throw "ERROR: El servidor PostgreSQL en '$containerName' no respondió positivamente a pg_isready tras $maxAttempts intentos."
    }
}
```

### 2.2. Despliegue de una nueva instancia aislada e inicialización segura

Si no existe una instancia previa en el host (o si en §2.1 no se detectó ningún contenedor candidato), se puede iniciar una instancia nueva dedicada para C04.
Esta ruta utiliza:
- Base de datos y usuario separados: `cooperadora`.
- Puerto nuevo por defecto en una variable independiente: `$C04_NEW_PG_PORT` (por defecto `55433`, preservando un override explícito pero sin heredar jamás el puerto de la ruta de reutilización), enlazado exclusivamente a loopback `127.0.0.1`.
- Nombre de contenedor independiente: `ps-cooperadora-c04-db`.
- Volumen de datos independiente: `ps_cooperadora_c04_data`.

> [!WARNING]
> **Comprobación previa de colisiones y persistencia**:
> Antes de ejecutar `docker run`, se debe verificar si ya existe un contenedor o un volumen con esos nombres.
> Si alguno ya existe, **no ejecute un contenedor duplicado ni elimine el volumen existente**: deténgase e inspeccione o reutilice la instancia existente.
> La imagen de PostgreSQL solo aplica las variables de inicialización (`POSTGRES_USER`, `POSTGRES_DB`, `POSTGRES_PASSWORD`) cuando el directorio de datos es nuevo/virgen. Si se reutiliza un volumen con datos preexistentes, la contraseña no se modificará y mantendrá la credencial con la que se inicializó dicho volumen.

Siempre se solicita de forma interactiva y segura una contraseña nueva para esta instancia, evitando heredar contraseñas residuales de I2 de una sesión previa en memoria.

```powershell
# 1. Comprobar colisiones previas: verificar si ya existe el contenedor o el volumen con esos nombres
$existingContainer = @(docker ps -a -q --filter "name=ps-cooperadora-c04-db")
if ($LASTEXITCODE -ne 0) {
    throw "ERROR: Falló el comando 'docker ps' al verificar colisión de contenedor (código de salida $LASTEXITCODE)."
}

$existingVolume = @(docker volume ls -q --filter "name=ps_cooperadora_c04_data")
if ($LASTEXITCODE -ne 0) {
    throw "ERROR: Falló el comando 'docker volume ls' al verificar colisión de volumen (código de salida $LASTEXITCODE)."
}

if ($existingContainer.Count -gt 0 -or $existingVolume.Count -gt 0) {
    throw "ERROR: Ya existe un contenedor ('ps-cooperadora-c04-db') o volumen ('ps_cooperadora_c04_data') previo. Detenga la ejecución e inspeccione/reutilice la instancia existente; no ejecute un contenedor duplicado ni borre el volumen. La imagen de PostgreSQL solo inicializa contraseñas en un directorio de datos nuevo."
}

# 2. Solicitar SIEMPRE una contraseña nueva de forma interactiva y segura para esta nueva instancia
# (evita heredar una contraseña residual de I2 de la sesión actual en memoria):
$securePass = Read-Host "Ingrese contraseña para la nueva instancia PostgreSQL (ps-cooperadora-c04-db)" -AsSecureString
$env:POSTGRES_PASSWORD = [System.Net.NetworkCredential]::new("", $securePass).Password

# 3. Configurar variables propias para la nueva instancia:
# Puerto independiente $C04_NEW_PG_PORT (por defecto 55433, preservando un override explícito si ya fue fijado) y base/usuario separados:
$C04_NEW_PG_PORT = if ($C04_NEW_PG_PORT) { $C04_NEW_PG_PORT } else { "55433" }
$C04_PG_DB       = "cooperadora"
$C04_PG_USER     = "cooperadora"

# 4. Iniciar contenedor pasando POSTGRES_PASSWORD heredada en el proceso (-e POSTGRES_PASSWORD sin literal en el comando),
# con enlace exclusivo a loopback 127.0.0.1:
docker run -d --name ps-cooperadora-c04-db `
  -e POSTGRES_DB=$C04_PG_DB `
  -e POSTGRES_USER=$C04_PG_USER `
  -e POSTGRES_PASSWORD `
  -p 127.0.0.1:${C04_NEW_PG_PORT}:5432 `
  -v ps_cooperadora_c04_data:/var/lib/postgresql/data `
  postgres:17-alpine

if ($LASTEXITCODE -ne 0) {
    throw "ERROR: Falló el comando 'docker run' al iniciar 'ps-cooperadora-c04-db' (código de salida $LASTEXITCODE). Verifique conflictos de puerto en 127.0.0.1:${C04_NEW_PG_PORT} o el estado del daemon Docker antes de esperar disponibilidad."
}

# 5. Asignar la variable común de puerto para la sección compartida de Django:
$C04_PG_PORT = $C04_NEW_PG_PORT

# 6. Bucle acotado de disponibilidad del servidor (server readiness)
# pg_isready valida únicamente la disponibilidad del servidor a nivel de red;
# la suite de integración de Django verificará las credenciales a nivel de aplicación.
$maxAttempts = 15
$attempt = 0
$serverReady = $false
while ($attempt -lt $maxAttempts) {
    $attempt++
    docker exec ps-cooperadora-c04-db pg_isready -U $C04_PG_USER -d $C04_PG_DB | Out-Null
    if ($LASTEXITCODE -eq 0) {
        $serverReady = $true
        Write-Host "Servidor PostgreSQL listo para aceptar conexiones (intento $attempt)."
        break
    }
    Start-Sleep -Seconds 1
}
if (-not $serverReady) {
    throw "ERROR: El servidor PostgreSQL 'ps-cooperadora-c04-db' no estuvo listo tras $maxAttempts intentos de pg_isready."
}
```

---

## 3. Preparación del entorno Python y configuración del proveedor

Activar el entorno virtual e instalar las dependencias:

```powershell
# Activar entorno virtual existente
.\.venv\Scripts\Activate.ps1

# Verificar versión de Python
python --version

# Instalar dependencias requeridas
pip install -r requirements/dev.txt
```

### Configuración del proveedor en settings

Para la integración C04, el proveedor documental se configura a nivel de servidor mediante:

```python
GASTOS_PAYMENT_DOCUMENT_PROVIDER = "documentos.c01.ProveedorDocumentalGastos"
```

La configuración del proyecto (`settings`) puede cargar automáticamente un archivo `.env` preexistente si estuviera presente, pero las variables de entorno de proceso establecidas para esta ejecución tienen precedencia. No inspeccione, cree, edite, versione ni muestre archivos `.env` ni su contenido.

```powershell
# Guardia explícita: verificar que se haya configurado una de las dos rutas de base de datos aislada (2.1 o 2.2).
# Evita caídas silenciosas a configuraciones por defecto; las variables explícitas del proceso tienen precedencia:
if (-not $C04_PG_PORT -or -not $C04_PG_DB -or -not $C04_PG_USER -or -not $env:POSTGRES_PASSWORD) {
    throw "ERROR: Parámetros de base de datos C04 no configurados. Debe ejecutarse la ruta 2.1 (reutilización I2) o 2.2 (nueva instancia) antes de continuar."
}

$env:POSTGRES_HOST = "127.0.0.1"
$env:POSTGRES_PORT = $C04_PG_PORT
$env:POSTGRES_DB = $C04_PG_DB
$env:POSTGRES_USER = $C04_PG_USER
# $env:POSTGRES_PASSWORD ya reside en memoria desde la asignación interactiva en la ruta seleccionada de §2 (§2.1 paso 5 o §2.2 paso 2).
$env:GASTOS_PAYMENT_DOCUMENT_PROVIDER = "documentos.c01.ProveedorDocumentalGastos"
```

---

## 4. Comandos de reproducción y verificación

> [!NOTE]
> **Resultados reportados el 2026-10-16 sobre el código `9cab2fd79580755e3e349fbcb49a4862d75272c7` (base `d65beda83e2bc056800c87778224c7fe23d06287`)**:
> Todas las ejecuciones de prueba utilizaron datos sintéticos y la instancia aislada de PostgreSQL 17 I2. Corresponden puntualmente a los comandos acotados listados a continuación, no a la suite de pruebas completa del repositorio:
> - Ruff: `ruff check --no-cache .` — sin hallazgos.
> - Django: `python manage.py check` — sin incidencias.
> - Migrations: `python manage.py makemigrations --check --dry-run` — sin cambios.
> - Focused integration: `python -m pytest tests/integracion/test_c04_pago_real_proyeccion.py -v` — 1 aprobada.
> - Regression: `python -m pytest tests/gastos tests/documentos tests/integracion/test_issue_28_proveedor_y_accesos.py -q` — 344 aprobadas en aproximadamente 58 s.
>
> **Comprobaciones focales adicionales ejecutadas el 2026-10-17 sobre ese mismo código:**
> - Configuración del proveedor: `python -m pytest tests/test_environment_configuration.py -q --tb=short` — 11 aprobadas; ejecución aislada, sin PostgreSQL.
> - Bloqueo PostgreSQL: `python -m pytest tests/integracion/test_bloqueo_documental.py -q --tb=short` — 1 aprobada en PostgreSQL 17 aislado. Se ejecutó por separado, por lo que no está incluida en las 344 regresiones ni en la prueba C04.
>
> **Estado de #49 al 2026-10-18 (corte histórico):** la rama local `feat/49-revision-documental-gastos` parte de main `48c094a45416c468c2f4ed3fa03b0ea6ed4e700b` y agrega una prueba focal del historial por versión. Ruff y `manage.py check` aprobaron en esa rama; las pruebas de integración no se ejecutaron porque PostgreSQL local no estaba disponible. La verificación posterior del 20/10 está en [`docs/evidence/i2-49-revision-gastos.md`](../evidence/i2-49-revision-gastos.md).

### 4.1. Verificación estática con Ruff y verificación de Django

```powershell
# Análisis estático de formato y estilo de código
ruff check --no-cache .

# Validar configuración general de Django
python manage.py check

# Verificar que no existen migraciones pendientes sin generar
python manage.py makemigrations --check --dry-run
```

### 4.2. Ejecución focalizada de la prueba de integración C04

Ejecutar la suite de integración C04 con el proveedor real:

```powershell
python -m pytest tests/integracion/test_c04_pago_real_proyeccion.py -v
```

### 4.3. Verificación de regresión en módulos vinculados

Ejecutar las suites de módulos vinculados, incluyendo el archivo de integración allí indicado:

```powershell
python -m pytest tests/gastos tests/documentos tests/integracion/test_issue_28_proveedor_y_accesos.py -q
```

### 4.4. Verificación focal de la configuración opcional del proveedor

La prueba carga copias aisladas de `settings.py` y comprueba ausencia, prioridad y limpieza
de valores en `.env` sintético y variables de proceso. No requiere PostgreSQL.

```powershell
python -m pytest tests/test_environment_configuration.py -q --tb=short
```

Resultado adicional del 2026-10-17 sobre `9cab2fd79580755e3e349fbcb49a4862d75272c7`:
11 pruebas aprobadas.

### 4.5. Verificación focal del bloqueo de versión en PostgreSQL

Esta prueba usa una conexión independiente para comprobar que el reemplazo de una versión
queda bloqueado hasta el commit de C01 y puede continuar después. Es adicional a la regresión
de 344 pruebas descrita arriba.

```powershell
python -m pytest tests/integracion/test_bloqueo_documental.py -q --tb=short
```

Resultado adicional del 2026-10-17 sobre `9cab2fd79580755e3e349fbcb49a4862d75272c7`, con
PostgreSQL 17 aislado: 1 aprobada.

### 4.6. Verificación de la proyección de revisiones por versión (#49)

La prueba focal cubre la proyección de cada versión documental y su historial, el permiso de
consulta de metadatos, la privacidad y la conservación del comportamiento del pago. Requiere
la instancia aislada de PostgreSQL descrita en §2.

```powershell
python -m pytest tests/integracion/test_49_proyeccion_revision_gastos.py -v
```

Este archivo se incluyó en una corrida focalizada combinada del 20/10/2026: 52 pruebas
aprobadas en seis archivos, según la nota de evidencia. No se ejecutó el archivo como
conjunto aislado ni se presenta la corrida como la suite completa.

---

## 5. Matriz de evidencia: Criterios GP-01 a GP-06 (SPEC-011)

Esta matriz distingue estrictamente lo verificado por la prueba de integración C04 de las garantías cubiertas por las suites unitarias y de integración preexistentes.

| Criterio | Comportamiento verificado en C04 (`test_c04_pago_real_proyeccion.py`) | Cobertura en suites preexistentes |
|---|---|---|
| **GP-01** — Separación de dimensiones | Verifica la consulta pre-pago (la cual no invoca las operaciones de listado ni de verificación del proveedor ni proyecta un pago; no se afirma que no se instancie un objeto proveedor) y post-pago, asegurando que `solicitud.estado == EstadoSolicitud.ACEPTADA` y `monto_estimado` se mantienen inalterados tras el registro. | En `tests/gastos/test_pago_externo_services.py`: `test_solo_gasto_aceptado_admite_pago` (exige estado aceptado), `test_decidir_no_concede_registrar_pago`, `test_gasto_visible_sin_permiso_da_403`, `test_consulta_sin_pago_retorna_none`. |
| **GP-02** — Vínculo documental y selector | Formulario GET `gastos:pagar` invoca `ProveedorDocumentalGastos.listar_opciones_para_pago` mediante spy real y expone en el selector la opción documental vigente tipada (`factura`). | En `tests/integracion/test_issue_28_proveedor_y_accesos.py`: `test_c01_traduce_catalogo_y_excluye_ticket` (excluye tickets del catálogo y rechaza pago con ticket), `test_c01_rechaza_una_factura_valida_de_otro_gasto` (rechaza factura de otra solicitud), `test_c01_rechaza_documento_facturacion_y_referencia_inexistente`. En `tests/gastos/test_pago_externo_services.py`: `test_evidencia_con_gasto_distinto_es_rechazada`, `test_evidencia_con_tipo_no_admitido_es_rechazada`, `test_evidencia_con_referencia_distinta_es_rechazada`. |
| **GP-03** — Registro atómico del hecho externo | En recorrido HTTP exitoso, registra atómicamente exactamente un `PagoExterno` y un `EventoPagoExterno`. Mediante spy real demuestra que `verificar_y_bloquear_documento` es invocado en el primer POST.<br>*Límite*: `test_c04` no verifica por sí solo rollbacks ni el bloqueo concurrente. | En `tests/gastos/test_pago_externo_services.py`: `test_rollback_completo_si_falla_la_creacion_del_evento` (garantiza rollback atómico completo si falla el evento), `test_fallo_del_proveedor_no_deja_escrituras` (ausencia de escrituras ante fallo documental). En `tests/integracion/test_issue_28_proveedor_y_accesos.py`: `test_c01_sin_transaccion_exterior_se_deniega`. En `tests/integracion/test_bloqueo_documental.py`: `test_verificacion_c01_bloquea_incluso_un_reemplazo_por_sql` verifica el bloqueo con una conexión independiente; se ejecutó por separado el 2026-10-17 sobre el código `9cab2fd79580755e3e349fbcb49a4862d75272c7` y aprobó (1 prueba), no incluida en las 344 regresiones reportadas. |
| **GP-04** — Idempotencia y conflicto | Reenvío idéntico produce redirección 302 sin duplicar pago ni evento. Reenvío con payload conflictivo (importe modificado) retorna HTTP 409 Conflicto sin crear pagos ni eventos adicionales (comprueba que los conteos de filas no aumentan). Demuestra mediante spy que ni el reenvío idéntico ni el conflictivo re-ejecutan `verificar_y_bloquear_documento` ni `listar_opciones_para_pago`. | En `tests/gastos/test_pago_externo_services.py`: `test_contenido_distinto_genera_conflicto` (comprueba mediante `refresh_from_db()` que el importe persistido permanece inalterado tras el conflicto, además de verificar los conteos de filas de pago y evento), `test_reenvio_identico_retorna_mismo_pago_sin_evento_nuevo`, `test_reenvio_identico_no_reconsulta_documento_ni_provider`, `test_huella_igual_pero_campo_distinto_no_es_idempotente`. |
| **GP-05** — Distinción de categoría y límites de revisión | La categoría del pago sigue siendo factual. La rama local #49 proyecta la revisión por versión en un panel independiente para actores autorizados; una revisión desconocida no equivale a aprobación. La corrida focalizada del 20/10 aprobó esa proyección con PostgreSQL aislado; Q4 institucional sigue pendiente y el criterio no se considera completo para #50. | En `tests/integracion/test_issue_28_proveedor_y_accesos.py`: `test_reemplazo_conserva_archivos_y_rechaza_version_obsoleta` (demuestra preservación de archivos y rechazo al intentar pagar con versión obsoleta). La evidencia nueva de #49 está en [`docs/evidence/i2-49-revision-gastos.md`](../evidence/i2-49-revision-gastos.md); la rama todavía no está integrada. |
| **GP-06** — Cronología, privacidad y degradación segura *(Cobertura parcial: localización de trámite pendiente)* | Las pruebas C04 verifican aserciones negativas en HTML (no filtración de UUID de versión, serie ni huella de idempotencia) y en `pago_consulta` (carece de `referencia_documental`), así como degradación segura. La corrida focalizada del 20/10 también aprobó la proyección de aportes y revisiones por versión en el historial.<br>*Brecha y límites*: `test_c04` no prueba por sí solo el nuevo panel, la navegación común ni la localización/búsqueda del trámite. PR #59 integró eventos/navegación comunes de #54; PR #62 integró DOC-R04 (#24). #28 conserva la integración conjunta de ambos circuitos y #50, el recorrido/evidencia manual final. | En `tests/gastos/test_pago_externo_services.py`: `test_consulta_pura_omite_referencia_documental` (demuestra que la consulta pura de servicio omite la referencia documental). En `tests/gastos/test_pago_externo_view.py`: `test_detalle_muestra_pago_y_cronologia_sin_referencia_documental` (comprueba la lista ordenada de hitos en el contexto `cronologia`: `[decision, pago]`), `test_error_de_decision_conserva_pago_y_cronologia_en_el_detalle`. En `tests/integracion/test_issue_28_proveedor_y_accesos.py`: `test_capacidad_pago_independiente_y_revocacion_en_consumidor_existente`, `test_descarga_directa_ajena_y_revocacion_facturacion`.<br>*Límite*: la evidencia de #49 cubre eventos y revisión por versión en el detalle; no acredita el recorrido manual de #50 ni el cruce de ambos circuitos que conserva #28.

---

## 6. Estado de implementación y cobertura
Estado de Issues/PR consultado el 20/10/2026. Los estados fechados en las notas previas se conservan como historia.


- **Estado de implementación y cobertura**: La integración C04 con el proveedor real `documentos.c01.ProveedorDocumentalGastos`, la derivación pura de categorías, la degradación segura fail-closed y la preservación estricta de garantías transaccionales de C03 están cubiertas por las pruebas reportadas sobre el código de PR #55. La revisión e historial documentales se integraron mediante PR #62 (#24). La proyección de ese historial en el detalle del gasto está implementada localmente en #49 y su corrida focalizada aprobó 52 pruebas en PostgreSQL 17.11 aislado. La rama aún no está integrada; GP-06 conserva cobertura parcial de navegación y localización del trámite. Véase la nota de la §4.
- **Distinción entre #49 y #50**: La Issue #49 abarca la integración del proveedor real, la derivación de categorías y la degradación en el circuito de pagos/gastos. La Issue #50 representa la preparación y consolidación de la evidencia completa de integración para revisión cruzada con Matías.
- **Límites de diseño DOC-R04 y preguntas Q1–Q5 (en especial Q4)**:
  - DOC-R04: La consulta e historial de revisiones están integrados en main mediante PR #62 (#24). La proyección en el detalle del gasto está implementada localmente en #49 y aprobó su validación focalizada en PostgreSQL; la rama aún no está integrada. Q4 sobre criterios institucionales de documentos definitivos sigue pendiente; los estados desconocidos no equivalen a aprobación.
  - Decisiones Q1–Q5: Criterios institucionales pendientes de validación con la administración de Cooperadora (incluyendo Q4 sobre requisitos documentales y comprobantes válidos).
- **Identidad del trámite integrada**: el vínculo OneToOne `SolicitudGasto.tramite_base` está disponible en main mediante PR #56 (#53 cerrada).
- **Pendientes para tramos posteriores (#28 / #49 / #50)**:
  - PR #59 integró la entrega #54 (eventos existentes adaptados a EventoHistorialDTO y navegación común) en main; la Issue #54 está cerrada. El handoff registra 40 pruebas aprobadas en PostgreSQL 17.11 aislado, Ruff y manage.py check.
  - #22 y #23 se cerraron mediante PR #60/#61. #28 continúa abierta para la integración conjunta de ambos circuitos.
  - #49 tiene validación focalizada aprobada en PostgreSQL, registrada en `docs/evidence/i2-49-revision-gastos.md`; su rama sigue pendiente de revisión e integración. La localización/búsqueda del trámite y el recorrido reproducible con registro manual de resultado para #50 siguen pendientes. La verificación focal de GP-02 (vínculo y accesos) y GP-03 (trazabilidad de un gasto) puede hacerse sobre el recorrido de gastos sin esperar #28; esta guía no afirma que se haya ejecutado ese recorrido manual.
  - Validación de preguntas de negocio institucionales Q1–Q5 con la administración de Cooperadora.
