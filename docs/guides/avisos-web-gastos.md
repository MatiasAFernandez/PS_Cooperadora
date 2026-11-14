# Avisos web y por correo de nuevas solicitudes de Gastos

Comportamiento y límites: [SPEC-028](../specs/028-franco-avisos-web-gastos.md) y [SPEC-029](../specs/029-franco-correo-nueva-solicitud-gastos.md).

## Preparación y configuración

Aplicar las migraciones con `python manage.py migrate` (incluye `avisos.0002` para las intenciones de correo). Los avisos web se generan al presentar solicitudes nuevas, con los adaptadores de identidad habilitados en el entorno.

El destinatario debe estar activo y tener las capacidades `gastos.consultar_todas` y `gastos.decidir`. Las cuentas locales también deben estar aprobadas y tener el correo verificado. Sin cuenta local se requiere identidad demo habilitada. La administración de cuentas y la lectura de Gastos por sí solas no habilitan avisos. Se excluye al autor de la solicitud.

El canal de correo está deshabilitado por defecto (`AVISOS_EMAIL_ENABLED=False`). Para habilitarlo en un entorno controlado, definir en variables de entorno del proceso (sin versionar credenciales ni `.env`):

- `AVISOS_EMAIL_ENABLED=True`
- `AVISOS_PUBLIC_BASE_URL`: URL raíz sin ruta, usuario, clave, consulta ni fragmento. En prueba local se permite HTTP de loopback explícito (por ejemplo, `http://127.0.0.1:8000` o `http://localhost:8000`); fuera de prueba local requiere `https://...`.
- `EMAIL_BACKEND`, `EMAIL_HOST`, `EMAIL_PORT`, `EMAIL_HOST_USER`, `EMAIL_HOST_PASSWORD`, `EMAIL_USE_TLS` y `DEFAULT_FROM_EMAIL` para el remitente.
- Para pruebas locales con Mailpit (SMTP en puerto `1025` y UI web en puerto `8026`), configurar `EMAIL_BACKEND=django.core.mail.backends.smtp.EmailBackend`, `EMAIL_HOST=127.0.0.1`, `EMAIL_PORT=1025`, `EMAIL_USE_TLS=False` y un remitente sintético en variables del proceso. Usar exclusivamente datos y direcciones sintéticas.

Activar `AVISOS_EMAIL_ENABLED`, migrar o ejecutar `reintentar_aviso_gasto` no genera ni envía correos retroactivos históricos.

## Recorrido

1. Presentar una solicitud de Gastos con una identidad solicitante.
2. Si `AVISOS_EMAIL_ENABLED=True`, tras confirmar la solicitud y los avisos web, se prepara una intención de correo por destinatario elegible y se envía un correo individual (texto y HTML) con asunto `[PS_Cooperadora] Nueva solicitud de gasto #N`, número, fecha de presentación en la zona horaria de la aplicación y el enlace protegido **Ver solicitud**.
3. Iniciar sesión con una identidad operadora habilitada y abrir **Avisos** en la navegación (o ingresar desde **Ver solicitud**). El contador muestra no leídos al cargar cada página; no se actualiza en tiempo real ni sustituye los pendientes operativos del circuito.
4. Usar **Todos** o **No leídos**. **Ver solicitud** abre el detalle con los permisos actuales de Gastos y no marca automáticamente el aviso como leído.
5. Usar **Marcar como leído** para actualizar sólo el aviso propio. La solicitud mantiene su estado y la lectura web no modifica el estado del correo.

La bandeja web funciona sin JavaScript; el contador de navegación requiere JavaScript. Ni los avisos web ni los correos incluyen importes, concepto, datos bancarios ni archivos adjuntos.

## Fallo de generación web y reintento (`reintentar_aviso_gasto`)

Un fallo de generación web se registra en el logger `avisos.services` con el número de solicitud y no revierte la solicitud confirmada. Tras resolver la causa, ejecutar:

```powershell
python manage.py reintentar_aviso_gasto 123
```

Reemplazar `123` por una solicitud existente. El comando evalúa los destinatarios actualmente autorizados y crea sólo avisos web faltantes; conserva la fecha de lectura de los existentes. No dispara envíos de correo ni debe usarse como carga histórica masiva.

## Estados de envío y operación (`correo_aviso_gasto`)

Cada intención de correo vinculada a un aviso web registra uno de seis estados:

- `pendiente` (**Pendiente**): preparada, aún no enviada.
- `en_proceso` (**En proceso**): reclamada para envío; puede conservarse tras una interrupción. El bloqueo PostgreSQL impide conciliar mientras el emisor siga activo.
- `aceptado` (**Aceptado por el servidor**): el servidor SMTP aceptó el mensaje. No garantiza entrega en buzón ni lectura, y no se reenvía al repetir el productor o el reintento.
- `fallido` (**Fallido**): fallo anterior a la entrega (por ejemplo, configuración inválida o conexión rechazada); es reintentable.
- `omitido` (**Omitido**): el destinatario dejó de cumplir identidad o permisos al intentar enviar. Una dirección ausente o inválida queda `fallido`, para corregirla antes de reintentar.
- `incierto` (**Incierto**): excepción durante la entrega o falta de confirmación persistida tras iniciarla; no garantiza entrega única (*exactly-once*) y requiere conciliación manual.

Las intenciones quedan persistidas, pero no hay worker ni recuperación automática ante caída del proceso: la consulta, reintento y conciliación se realizan manualmente con `correo_aviso_gasto`. Los logs registran identificadores y códigos acotados, sin excepciones crudas, cuerpos, credenciales ni direcciones de correo.

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
