# Avisos web y por correo de Gastos

Comportamiento y límites: [SPEC-028](../specs/028-franco-avisos-web-gastos.md), [SPEC-029](../specs/029-franco-correo-nueva-solicitud-gastos.md) y [SPEC-030](../specs/030-franco-avisos-decision-gastos.md).

## Preparación y configuración

Aplicar las migraciones con `python manage.py migrate` (incluye `avisos.0002` para las intenciones de correo y `avisos.0003` para avisos de decisiones). Los avisos web se generan al presentar solicitudes nuevas y al registrar decisiones confirmadas, con los adaptadores de identidad habilitados en el entorno.

Autorización vigente por tipo de evento en la bandeja, el contador y el envío por correo:

- **Nueva solicitud a operadores:** destinatario activo con `gastos.consultar_todas` y `gastos.decidir`, excluyendo al autor de la solicitud.
- **Decisión de gasto al titular:** destinatario activo igual al `solicitante` de la solicitud, con visibilidad efectiva sobre esa solicitud (`gastos.consultar_propias` o `gastos.consultar_todas`). No exige `gastos.decidir`.
- **Bandeja y contador:** visibles para identidades con `gastos.consultar_propias` o `gastos.consultar_todas`. Una identidad de solo lectura sin solicitudes propias ve la bandeja vacía y no accede a avisos operativos de nuevas solicitudes.
- Las cuentas locales también deben estar aprobadas y tener el correo verificado. Sin cuenta local se requiere identidad demo habilitada. La administración de cuentas, `is_staff` o `is_superuser` por sí solos no habilitan avisos.

El canal de correo está deshabilitado por defecto (`AVISOS_EMAIL_ENABLED=False`). Para habilitarlo en un entorno controlado, definir en variables de entorno del proceso (sin versionar credenciales ni `.env`):

- `AVISOS_EMAIL_ENABLED=True`
- `AVISOS_PUBLIC_BASE_URL`: URL raíz sin ruta, usuario, clave, consulta ni fragmento. En prueba local se permite HTTP de loopback explícito (por ejemplo, `http://127.0.0.1:8000` o `http://localhost:8000`); fuera de prueba local requiere `https://...`.
- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` y `DEFAULT_FROM_EMAIL` para el remitente.
- Para pruebas locales con Mailpit (SMTP en puerto `1025` y UI web en puerto `8026`), configurar `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST=127.0.0.1`, `EMAIL_PORT=1025`, `EMAIL_USE_TLS=False` y un remitente sintético en variables del proceso. Usar exclusivamente datos y direcciones sintéticas.

Activar `AVISOS_EMAIL_ENABLED`, migrar o ejecutar `reintentar_aviso_gasto` o `reintentar_aviso_decision_gasto` no genera ni envía correos retroactivos históricos.

## Recorrido

1. Presentar una solicitud de Gastos con una identidad solicitante.
2. Si `AVISOS_EMAIL_ENABLED=True`, tras confirmar la solicitud y los avisos web, se prepara una intención de correo por operador elegible y se envía un correo individual (texto y HTML) con asunto `[PS_Cooperadora] Nueva solicitud de gasto #N`, número, fecha de presentación en la zona horaria de la aplicación y el enlace protegido **Ver solicitud**.
3. Registrar una decisión (`Aceptada`, `Postergada` o `Rechazada`) con una identidad operadora habilitada. Si la decisión se confirma, se genera un aviso web por `DecisionGasto` para el titular y, si `AVISOS_EMAIL_ENABLED=True`, se envía un correo individual (texto y HTML) con asunto `[PS_Cooperadora] Decisión sobre solicitud de gasto #N`, resultado y fecha de esa decisión y el enlace **Ver solicitud** (sin motivo de decisión ni datos sensibles).
4. Los avisos de decisión informan un hecho histórico (`El ... se registró la decisión ...`), separado del estado actual de la solicitud: una postergación previa conserva su aviso propio aunque luego la solicitud sea aceptada o rechazada.
5. Iniciar sesión con una identidad habilitada (`gastos.consultar_propias` o `gastos.consultar_todas`) y abrir **Avisos** en la navegación (o ingresar desde **Ver solicitud**). El contador muestra no leídos al cargar cada página; no se actualiza en tiempo real ni sustituye los pendientes operativos del circuito.
6. Usar **Todos** o **No leídos**. **Ver solicitud** abre el detalle con los permisos actuales de Gastos y no marca automáticamente el aviso como leído.
7. Usar **Marcar como leído** para actualizar sólo el aviso propio. La solicitud mantiene su estado y la lectura web no modifica el estado del correo.

La bandeja web funciona sin JavaScript; el contador de navegación requiere JavaScript. Ni los avisos web ni los correos incluyen importes, concepto, datos bancarios, motivo de decisión ni archivos adjuntos.

## Fallo de generación web y reintento (`reintentar_aviso_gasto` / `reintentar_aviso_decision_gasto`)

Un fallo de generación web se registra en el logger `avisos.services` con el identificador correspondiente y no revierte la solicitud ni la decisión confirmadas. Tras resolver la causa, ejecutar según el evento:

```powershell
python manage.py reintentar_aviso_gasto 123
python manage.py reintentar_aviso_decision_gasto 456
```

Reemplazar `123` por una solicitud existente o `456` por una `DecisionGasto` existente. Cada comando evalúa los destinatarios actualmente autorizados y crea sólo avisos web faltantes de forma idempotente; conserva la fecha de lectura de los existentes. No prepara ni dispara envíos de correo ni debe usarse como carga histórica masiva.

## Estados de envío y operación (`correo_aviso_gasto`)

Cada intención de correo vinculada a un aviso web registra uno de seis estados:

- `pendiente` (**Pendiente**): preparada, aún no enviada.
- `en_proceso` (**En proceso**): reclamada para envío; puede conservarse tras una interrupción. El bloqueo PostgreSQL impide conciliar mientras el emisor siga activo.
- `aceptado` (**Aceptado por el servidor**): el servidor SMTP aceptó el mensaje. No garantiza entrega en buzón ni lectura, y no se reenvía al repetir el productor o el reintento.
- `fallido` (**Fallido**): fallo anterior a la entrega (por ejemplo, configuración inválida o conexión rechazada); es reintentable.
- `omitido` (**Omitido**): el destinatario dejó de cumplir identidad o permisos al intentar enviar. Una dirección ausente o inválida queda `fallido`, para corregirla antes de reintentar.
- `incierto` (**Incierto**): excepción durante la entrega o falta de confirmación persistida tras iniciarla; no garantiza entrega única (*exactly-once*) y requiere conciliación manual.

Las intenciones quedan persistidas, pero no hay worker ni recuperación automática ante caída del proceso: la consulta, reintento y conciliación se realizan manualmente con `correo_aviso_gasto` (que abarca tanto avisos de nueva solicitud como de decisión vinculados a esa solicitud, mostrando `tipo=` y `decision=`). Los logs registran identificadores y códigos acotados, sin excepciones crudas, cuerpos, credenciales ni direcciones de correo.

### Consultar estado

En los comandos siguientes, reemplazar `<solicitud_id>` y `<intencion_id>` por sus números correspondientes antes de ejecutar.

```powershell
python manage.py correo_aviso_gasto <solicitud_id>
```

### Reintentar pendientes o fallidos

```powershell
python manage.py correo_aviso_gasto <solicitud_id> --reintentar
```

Revalida identidad, permisos y dirección antes de enviar; omite los `aceptado`, `omitido`, `incierto` y `en_proceso`.

### Conciliar `incierto` o `en_proceso`

Antes de conciliar, corroborar en la UI de Mailpit (puerto `8026` en prueba local) o en el servidor SMTP si el mensaje fue recibido, y verificar que no haya un emisor activo:

- Si el correo figura en Mailpit:

```powershell
python manage.py correo_aviso_gasto <solicitud_id> --conciliar-envio <intencion_id> --resultado aceptado
```

- Si el correo no figura en Mailpit y se autoriza reenviar asumiendo riesgo de duplicado:

```powershell
python manage.py correo_aviso_gasto <solicitud_id> --conciliar-envio <intencion_id> --resultado reintentar --confirmar-riesgo-duplicado
python manage.py correo_aviso_gasto <solicitud_id> --reintentar
```

La verificación visual de la plantilla HTML en Mailpit (escritorio y ancho móvil `390px`) queda pendiente de QA integrado.
