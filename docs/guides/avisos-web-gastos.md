# Avisos web de nuevas solicitudes de Gastos

Comportamiento y límites: [SPEC-028](../specs/028-franco-avisos-web-gastos.md).

## Preparación

Aplicar las migraciones con `python manage.py migrate`. Los avisos se generan al
presentar solicitudes nuevas, con los adaptadores de identidad habilitados en el
entorno. No se cargan avisos retroactivos automáticamente.

El destinatario debe estar activo y tener las capacidades `gastos.consultar_todas`
y `gastos.decidir`. Las cuentas locales también deben estar aprobadas y tener el
correo verificado. Sin cuenta local se requiere identidad demo habilitada. La
administración de cuentas y la lectura de Gastos por sí solas no habilitan avisos.
Se excluye al autor de la solicitud.

## Recorrido

1. Presentar una solicitud de Gastos con una identidad solicitante.
2. Iniciar sesión con una identidad operadora habilitada y abrir **Avisos** en la
   navegación. El contador muestra no leídos al cargar cada página; no se actualiza
   en tiempo real ni sustituye los pendientes operativos del circuito.
3. Usar **Todos** o **No leídos**. **Ver solicitud** abre el detalle con los permisos
   actuales de Gastos y no marca automáticamente el aviso.
4. Usar **Marcar como leído** para actualizar sólo el aviso propio. La solicitud
   mantiene su estado. Los avisos leídos permanecen en **Todos**.

La bandeja funciona sin JavaScript; el contador de navegación requiere JavaScript.
Los avisos no incluyen importes, concepto, datos bancarios ni archivos.

## Fallo de generación y reintento

Un fallo de generación se registra en el logger `avisos.services` con el número de
solicitud y no revierte la solicitud confirmada. Tras resolver la causa, ejecutar
en el entorno correspondiente:

```powershell
python manage.py reintentar_aviso_gasto 123
```

Reemplazar `123` por una solicitud existente. El comando evalúa los destinatarios
actualmente autorizados y crea sólo avisos faltantes; conserva la fecha de lectura
de los existentes. No usarlo como carga histórica masiva sin definir ese alcance.
Si no hay destinatarios elegibles, cero avisos es un resultado válido.

No hay cola durable ni recuperación automática si el proceso cae entre confirmar
la solicitud y generar el aviso. El canal de correo, recordatorios y otros eventos
quedan para incrementos posteriores según la especificación del hito.
