# SPEC-031 — Avisos del registro inicial de pago externo

Fecha: 14/11/2026. Responsable: Franco Damián Sánchez (Gastos/pagos).
Estado: especificación para revisión previa a implementación.
Seguimiento: [#132](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/132).
Base: [SPEC-028](028-franco-avisos-web-gastos.md),
[SPEC-029](029-franco-correo-nueva-solicitud-gastos.md) y
[SPEC-030](030-franco-avisos-decision-gastos.md).

## Valor y límites

Informar al titular cuando se registra por primera vez un pago externo de su
solicitud, por aviso web y correo habilitado. Se comunica un registro de la
aplicación, no la ejecución de una transferencia ni una confirmación bancaria.

No cambia reglas, importes, permisos ni documentos del pago. Se conserva el
[contrato de pago externo](../contracts/i2-pago-externo.md), contrastándolo con el
servicio vigente y sus actualizaciones posteriores. Las rectificaciones, aportes
posteriores de comprobantes/ATP y avisos documentales quedan para otro tramo en
[#128](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/128); no se eliminan.
No incluye pagos parciales nuevos, emisión fiscal ni SMTP productivo.

## Fuente y momento del evento

1. Fuente: `EventoPagoExterno.pk`, de tipo `pago_externo_registrado`, relacionado
   mediante `pago.solicitud_id`. No usar el estado mutable de la solicitud, ni una
   rectificación posterior, como señal de un nuevo pago inicial.
2. Productor: `gastos.payments.registrar_pago_externo`, únicamente en el camino
   que crea pago, evento y `PagoExternoOriginal`. Registrar el callback después de
   completar esas escrituras, dentro de la operación existente, antes de retornar.
   El camino de reenvío idéntico que devuelve el pago existente no programa otro
   aviso. Una diferencia que genera conflicto conserva ese comportamiento.
3. `operacion_documental` mantiene la propiedad de la transacción exterior y la
   compensación de archivos. Generar el aviso después del commit efectivo, usando
   `transaction.on_commit`; no introducir otra transacción exterior ni SMTP dentro
   del registro/documentación del pago.
4. Validación fallida, denegación, conflicto, fallo documental o rollback no generan
   aviso ni correo. Un fallo posterior de generación o SMTP no revierte el pago,
   no elimina documentos y no se propaga a `operacion_documental` como si hubiera
   fallado el registro. Se informa con IDs/códigos seguros y recuperación manual.
5. Un aviso por evento y titular. Reproducir ese evento no duplica avisos ni
   intenciones, no reenvía aceptados y conserva la fecha de lectura. Una migración
   no convierte pagos ya existentes en notificaciones nuevas.

## Destinatario y autorización

Único destinatario: `SolicitudGasto.solicitante_id`, con identidad operativa y
acceso efectivo al gasto según `visible_expenses(actor)`, igual que para decisiones
propias. No exige `gastos.registrar_pago` ni `gastos.decidir` al titular para leer
su aviso. Tener lectura global no permite ver avisos de otros destinatarios.

La autorización verifica en servidor el encadenamiento evento→pago→solicitud y
la titularidad, sin aceptar referencias o destinatarios desde el cliente. Tipos
de evento desconocidos, fuentes inexistentes o relaciones cruzadas se excluyen.
No se aplica la exclusión del autor de solicitud del aviso de nueva solicitud.
Que el registrador coincida con el titular no cambia las reglas actuales del pago.

La matriz compartida cubre generación, bandeja, contador, marcado y envío/reintento.
Se mantienen reglas de identidad local/demo; staff/superusuario y administración
de cuentas no conceden facultades implícitas. Pérdida de permisos/actividad produce
Omitido al intentar enviar una intención existente; dirección inválida produce
Fallido reintentable, según SPEC-029. Se revalida al reintentar, sin enviar al
beneficiario, proveedor o correo informado para comprobantes.

## Contenido y experiencia

- Web: **Pago externo registrado**, número de solicitud y fecha/hora de registro
  tomada de `EventoPagoExterno.fecha_hora`. La fecha del aviso se distingue cuando
  se recupera posteriormente. No usar `fecha_pago` ni datos efectivos rectificados
  para reconstruir este hecho histórico.
- Correo individual, texto y HTML: asunto `[PS_Cooperadora] Registro de pago externo
  de solicitud de gasto #N`. Cuerpo: «El ... se registró un pago externo para la
  solicitud #N», botón **Ver solicitud** y enlace alternativo protegido.
- Sin concepto, importes bruto/neto/ATP, datos bancarios, referencias financieras,
  motivos, nombres de archivos ni adjuntos. El detalle conserva sus propios permisos
  para consultar documentos y datos; el aviso no amplía acceso ni cambia el trámite.
- Una rectificación posterior no reemplaza ni transforma el aviso original. El
  mensaje conserva la fecha del registro inicial y el enlace abre el detalle e
  historial vigentes. No se presenta un importe histórico o actual en el mensaje.
- Reutilizar bandeja, contador de una consulta al cargar y marcado individual por
  POST con CSRF. Abrir el enlace no marca leído. Mantener filtros, paginación de
  25 y composición actual según la [guía visual](../visual-guide/README.md).

## Persistencia y recuperación compatibles

Agregar el tipo de aviso y una referencia estable al evento inicial de pago, con
unicidad/coherencia por tipo. Conservar IDs, lecturas, intenciones y restricciones
de nueva solicitud y decisiones. Referencias de fuentes distintas no se mezclan;
una migración aditiva no requiere recrear el historial ni un bus general de eventos.

Reutilizar `IntencionCorreo`, estados, bloqueo PostgreSQL, validación de URL y
remitente, reintento y conciliación ya implementados. El productor crea intención
sólo junto con un aviso nuevo si `AVISOS_EMAIL_ENABLED=True`; confirma ambos antes
de enviar. Sin cola/worker ni recuperación automática tras interrupciones; no se
promete exactamente una entrega SMTP ni recepción real por aceptación del servidor.

Extender el comando de correo por solicitud al nuevo tipo reconocido, mostrando
el tipo y su fuente. Incluir recuperación web explícita por ID del evento de pago,
que no prepare ni envíe correo. Los comandos web de nueva solicitud y decisión
conservan su alcance. Activar el canal, migrar o recuperar avisos web no envía
históricos; inciertos/en proceso siguen requiriendo conciliación explícita que no
pueda quitar la exclusión a un emisor activo.

## Verificación y entrega

Revisión estática de Gemini por CLI antes del código. Dos incrementos: productor,
persistencia, permisos y recuperación; luego presentación, plantilla y guía.

Pruebas con registro real y commit efectivo: pago/evento/original/documentos
persistidos antes de generar/enviar; fallo del aviso después del commit conserva
todo y no hace fallar la operación documental. Cubrir reenvío idéntico, conflicto,
rollback/fallo de storage y registro no autorizado sin avisos. Comprobar canal
apagado, permiso revocado, usuario inactivo, relaciones cruzadas e IDs ajenos.

Verificar deduplicación, lectura independiente, fallo SMTP/reintento y separación
de recuperación web/correo. Rectificar o aportar constancia después no genera ni
altera el aviso inicial; un reenvío idéntico al alta original tras rectificar sigue
sin duplicar, respetando la idempotencia existente del servicio.

Regresión de avisos de nueva solicitud y decisiones, pruebas de pago/documentos
pertinentes y CI. QA Desktop/Mailpit comprueba registro desde UI, destinatario,
contenido, enlace protegido y escritorio/móvil. Registrar versión, método y límites
en la PR; no convertir prueba sintética en conformidad institucional. Actualizar la
guía de uso/comandos al implementar y conservar los otros aplazamientos en #128.
