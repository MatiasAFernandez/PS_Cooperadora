# SPEC-028 — Avisos web de nuevas solicitudes de Gastos

Fecha: 14/11/2026. Responsable del evento y destinatarios de Gastos:
Franco Damián Sánchez. Validación operativa institucional pendiente.
Seguimiento: [Issue #125](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/125).
Referencia: [SPEC-015](015-matias-avisos-pendientes.md). Este incremento propone
una base mínima compartible, sin modificar Facturación ni definir sus eventos.

## Resultado y alcance

Una solicitud de Gastos presentada genera un aviso persistente para cada operador
activo que pueda consultar todas las solicitudes y decidirlas. Se excluye al autor.
Se respetan los adaptadores de identidad habilitados: una cuenta local requiere
aprobación y correo verificado; una cuenta sin identidad local requiere demo
habilitada. Staff, superusuario, lectura y administración de cuentas por sí solos
no autorizan la recepción.

El aviso comunica un hecho ocurrido; los pendientes operativos existentes siguen
mostrando trabajo por resolver. Leer un aviso no decide ni cambia la solicitud.

## Comportamiento y aceptación

1. La generación parte del servicio de creación, sólo después de confirmar la
   transacción. Una reversión no deja avisos. Reproducir el evento de una misma
   solicitud no duplica avisos del mismo destinatario. Esto no convierte dos
   solicitudes distintas en una sola ni cambia la idempotencia del formulario.
2. El contenido mínimo identifica el número de solicitud, fecha y hecho ocurrido;
   no incluye concepto, datos bancarios, importes, adjuntos ni credenciales.
3. La bandeja propia ofrece Todos / No leídos, orden reciente y 25 elementos por
   página. Distingue leído/no leído con texto además del color. Tiene estado vacío
   claro y enlace al detalle protegido por los permisos vigentes de Gastos.
4. Los GET no marcan como leído. Un POST con CSRF permite marcar individualmente;
   repetirlo no cambia la fecha original. No se aceptan destinatarios ni destinos
   de redirección arbitrarios del cliente. Un identificador ajeno no revela datos.
5. Bandeja, contador y marcado revalidan identidad y las dos capacidades actuales.
   Una sesión que pierde permisos deja de acceder a los avisos de este evento.
6. La navegación ofrece Avisos y contador de no leídos mediante una consulta HTTP
   al cargar la página, sin sondeo periódico ni consultas de avisos incorporadas
   al renderizado de todas las vistas. Sin JavaScript se puede usar la bandeja.
7. Una generación fallida se registra sin contenido sensible y no revierte la
   solicitud confirmada. Un comando por número de solicitud permite reintentar
   idempotentemente, evaluando destinatarios autorizados al ejecutar el reintento.
   No se promete entrega automática ante caída de proceso entre commit y aviso;
   no hay cola durable ni recuperación automática en este incremento.

## Interfaz y verificación

Reutilizar layout, navegación, tokens y patrones de bandeja actuales según la
[guía visual](../visual-guide/README.md). Acciones con nombres claros, foco visible,
estado vacío y composición sin desborde a 1366×900 y 390×844.

Pruebas focalizadas: destinatarios locales/demo y exclusiones, flags de identidad,
evento repetido, reversión, fallo/reintento, aislamiento por destinatario, permisos
revocados, CSRF, GET sin mutación, POST repetido, filtros y paginación. QA Desktop
verifica el recorrido real con dos identidades y escritorio/móvil; su resultado
se registra en la PR, separado de las pruebas automatizadas.

## Continuidad y límites

El siguiente incremento se define en [SPEC-029](029-franco-correo-nueva-solicitud-gastos.md):
correo para este mismo evento, con Mailpit y fallos observables. Otros eventos de
Gastos, Facturación y cuentas requieren su
matriz de destinatarios y aceptación específica. Se difieren recordatorios
programados, preferencias avanzadas, adjuntos por correo y envío productivo:
aportan valor, pero no son necesarios para comprobar este recorrido acotado y
requieren decisiones adicionales de operación/configuración.
El seguimiento de esos aplazamientos se conserva en
[#128](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/128).
