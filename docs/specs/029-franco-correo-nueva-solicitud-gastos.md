# SPEC-029 — Correo de nueva solicitud de Gastos

Fecha: 14/11/2026. Responsable principal: Franco Damián Sánchez (Gastos).
Comportamiento integrado por [#129](https://github.com/MatiasAFernandez/PS_Cooperadora/pull/129).
Estado de seguimiento y verificación: Issue/PR vinculadas; no representa activación productiva.
Guía operativa: [Avisos web y por correo de nuevas solicitudes de Gastos](../guides/avisos-web-gastos.md).
Seguimiento: [#127](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/127).
Base: [SPEC-028](028-franco-avisos-web-gastos.md), integrada por #126.
La identidad conserva su contrato; no se modifican Facturación ni sus eventos.
La validación técnica no equivale a aceptación operativa institucional.

## Problema, alcance y continuidad

La bandeja web requiere entrar a la aplicación para conocer una solicitud nueva.
Este incremento agrega correo para ese mismo hecho, sin cambiar el trámite ni el
estado leído/no leído del aviso web. No envía por cada edición de la solicitud.

Otros eventos, recordatorios, preferencias, adjuntos y SMTP productivo permanecen
registrados con valor, motivo de aplazamiento y condición de reanudación en
[#128](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/128). Completar
#127 no resuelve esos pendientes. Los correos de verificación, recuperación e
invitación existentes se conservan y no se implementan nuevamente.

## Destinatarios y contenido

- Un correo individual por aviso de nueva solicitud y destinatario, sin exponer
  direcciones de otros operadores mediante Para/CC. Se excluye al autor.
- Se reutilizan las reglas de identidad y las capacidades `gastos.consultar_todas`
  y `gastos.decidir`. Al intentar el envío se vuelve a comprobar usuario activo,
  adaptador habilitado, aprobación/verificación local cuando corresponda y permisos.
  Staff, superusuario, lectura o administración de cuentas por sí solos no bastan.
- La dirección procede del actor resuelto: correo verificado de CuentaLocal o
  correo del usuario demo autorizado. No se acepta una dirección desde el POST del
  trámite ni se usa la del beneficiario. Dirección ausente/inválida impide enviar.
- Asunto: `[PS_Cooperadora] Nueva solicitud de gasto #N`. Cuerpo en texto y HTML
  con número, fecha de presentación y acción **Ver solicitud**. Fecha con zona
  horaria de la aplicación; sin concepto, importe, datos bancarios ni adjuntos.
- El enlace se construye en servidor con URL base configurada y ruta de Gastos,
  nunca con un host o destino arbitrario de la petición. No contiene credenciales
  ni concede permisos. Sin sesión se aplica el acceso existente; con sesión sin
  facultades se deniega. Abrirlo no marca el aviso como leído ni decide el gasto.
- HTML sencillo, identidad visual coherente con la guía vigente, texto legible y
  enlace alternativo visible; comprobar escritorio y ancho móvil en Mailpit.

## Envío y estado observable

1. El canal requiere habilitación explícita, deshabilitada por defecto mediante
   `AVISOS_EMAIL_ENABLED`. Reutiliza `EMAIL_*` y `DEFAULT_FROM_EMAIL`; la URL base
   propia se configura en `AVISOS_PUBLIC_BASE_URL`. No cambia `.env` ni contrata
   proveedores. La prueba usa exclusivamente direcciones sintéticas y Mailpit.
   La URL debe apuntar a la raíz, sin usuario, clave, consulta ni fragmento; HTTPS
   fuera de la prueba local, donde se permite HTTP de loopback explícito.
2. La intención de envío se guarda vinculada al aviso web, con unicidad por aviso.
   Primero se confirma la persistencia de los avisos y sus intenciones; después se
   intenta enviar. Un fallo de SMTP no elimina avisos ni revierte la solicitud.
   No se realiza envío dentro de la transacción de creación del trámite.
3. Sólo se preparan intenciones para avisos creados con el canal habilitado. No se
   envían correos retroactivos al activar la opción, migrar o ejecutar el comando
   existente de recuperación web. Un cambio de configuración no inicia una campaña.
4. Estados mínimos: **Pendiente**, **En proceso**, **Aceptado por el servidor**,
   **Fallido**, **Omitido** e **Incierto**. Conservar cantidad de intentos, fechas,
   dirección usada en el intento y código de resultado acotado. No guardar cuerpo,
   credenciales ni respuestas SMTP completas en el registro de errores.
5. Antes de la operación de envío se reclama atómicamente la intención y se guarda
   **En proceso**, evitando dos emisores simultáneos para el mismo aviso. Los
   aceptados no se reenvían por repetir el productor o el comando de reintento.
6. Un resultado positivo del backend significa aceptación por el servidor, no
   recepción, lectura ni garantía contra spam. La lectura web es independiente.
   Un fallo inequívoco anterior a entregar el mensaje —por ejemplo, configuración
   inválida o imposibilidad de abrir conexión— queda **Fallido** y es reintentable.
   Una cuenta que ya no cumple los permisos queda **Omitido**, sin envío.
7. Una excepción durante la entrega o la falta de confirmación persistida después
   de iniciarla deja resultado **Incierto**. Un proceso interrumpido puede conservar
   **En proceso**; se informa para conciliación, sin convertirlo automáticamente
   en fallido ni volver a enviarlo. No se promete exactamente una entrega SMTP.
8. Un comando operativo permite consultar estados y reintentar por solicitud sólo
   pendientes/fallidos, revalidando identidad y dirección. La configuración de un
   destinatario puede corregirse antes de ese intento. Un envío aceptado no se
   redirige automáticamente a otra dirección por un cambio posterior.
9. Inciertos o procesos interrumpidos requieren comprobar el servidor de pruebas y
   una acción explícita de conciliación, separada del reintento normal. Si se
   autoriza reenviarlos, el comando debe advertir y exigir una opción explícita
   por el riesgo de duplicado; no liberar un intento que siga ejecutándose.
10. El estado se consulta mediante el comando, con identificadores y resultados
    mínimos; los logs no incluyen destinatarios, cuerpo ni secretos. No se agrega
    una consola administrativa web ni se muestran errores SMTP al solicitante.

## Interfaces y proporcionalidad

La intención por aviso justifica un registro persistente pequeño en `avisos`:
permite observar fallos y excluir aceptados al reintentar. No es un bus de eventos
ni un planificador general. Usar el backend de correo de Django, sin Celery,
servicios de colas, seguimiento de aperturas ni preferencias nuevas.

Se conserva `reintentar_aviso_gasto` como recuperación del canal web. La operación
de correo debe distinguirse explícitamente, para no enviar al ejecutar una tarea
que antes sólo generaba avisos web. La ausencia de cola/worker conserva el límite
de recuperación manual tras interrupciones; un fallo de un destinatario no impide
intentar los restantes ni altera la bandeja y el contador existentes.

## Criterios de aceptación y entrega

- Solicitud válida produce aviso y correo mínimo en Mailpit para operadores
  elegibles; rollback no produce ninguno. Canal apagado no prepara ni envía correo.
- Permisos revocados, cuenta inactiva/pendiente/no verificada, autor y roles sin
  facultades no reciben correo; el reintento vuelve a comprobarlos.
- Repetición y concurrencia no vuelven a enviar aceptados. Fallo de conexión,
  resultado incierto e interrupción tienen estados y salidas operativas distintos.
- Correo fallido conserva solicitud y aviso web; reintento no duplica esos objetos
  ni modifica lectura. No hay envío histórico accidental con migración/activación.
- Configuración y URL inválidas fallan de forma observable sin construir enlaces
  desde Host del cliente. Se mantiene acceso protegido al destino.
- Pruebas focalizadas y regresión de avisos web; QA en Mailpit comprueba contenido,
  presentación y enlace real, distinguiendo navegador, HTTP, BD y simulación SMTP.
- Guía de configuración, comandos y conciliación actualizada al implementar. Dos
  tramos de trabajo: persistencia/envío/recuperación; plantilla y QA de integración.
  Publicar commits coherentes. El código requiere revisión del plan de permisos,
  persistencia y resultados inciertos antes de implementarlo; no basta esta spec
  para declarar completada la Issue.
