# SPEC-030 — Avisos de decisiones de Gastos al solicitante

Fecha: 14/11/2026. Responsable: Franco Damián Sánchez (Gastos).
Estado: especificación para revisión previa a implementación.
Seguimiento: [#130](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/130).
Base: [SPEC-028](028-franco-avisos-web-gastos.md) y
[SPEC-029](029-franco-correo-nueva-solicitud-gastos.md).
No modifica identidad, Facturación ni las reglas institucionales pendientes.

## Valor y límites

Completar la comunicación: los operadores conocen las solicitudes nuevas y el
titular recibe el resultado de la decisión, por web y correo habilitado. Se
reutilizan bandeja, contador, lectura y recuperación existentes.

Otros eventos y funcionalidades aplazadas conservan motivo y condición de
reanudación en [#128](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/128).
No se implementan pagos, documentos, Facturación, cuentas, recordatorios,
preferencias ni SMTP productivo como parte de este tramo.

## Evento y transiciones

La fuente es cada `DecisionGasto` persistida por `decide_expense`, no una lectura
del estado actual de `SolicitudGasto`. Se conservan las transiciones vigentes:

| Estado anterior | Decisiones permitidas |
|---|---|
| Presentada | Aceptada, Postergada, Rechazada |
| Postergada | Aceptada, Rechazada |
| Aceptada o Rechazada | Sin nueva decisión en este servicio |

No se agrega otra postergación, corrección, reapertura ni plazo. Se mantienen
validación de motivo, conflicto de versión, permisos y prohibición vigente de
decisión propia. Notificar no ejecuta ni registra un pago.

1. Programar la generación sólo por una decisión nueva confirmada, después del
   commit efectivo. Un rollback, entrada inválida, decisión no autorizada o
   conflicto no genera avisos ni correo.
2. Identificar el evento por `DecisionGasto.pk`. Una postergación y la aceptación
   posterior generan dos avisos distintos para el mismo titular. Reproducir una
   decisión ya notificada no crea duplicados, correos nuevos ni reinicia lectura.
3. La persistencia debe admitir varias decisiones por solicitud sin debilitar la
   unicidad ya existente del aviso de nueva solicitud. Conservar IDs, lecturas e
   intenciones previas con migración aditiva, sin notificar decisiones históricas.
4. Un fallo al generar o enviar el aviso no revierte la decisión confirmada. Los
   resultados y recuperación manual conservan los límites de SPEC-028/029; no se
   agrega una cola o un bus general de eventos.

## Destinatario y autorización por evento

El único destinatario de una decisión es el usuario de `solicitud.solicitante_id`.
No se toma su dirección de un formulario ni la del beneficiario. Se comprueba
identidad vigente con el adaptador existente y acceso efectivo a esa solicitud
mediante `visible_expenses(actor)`, además de la titularidad por ID.

| Tipo de aviso | Autorización vigente para recibir, consultar, contar y marcar |
|---|---|
| Nueva solicitud a operadores | Mantiene ambas capacidades: consultar todas y decidir; autor excluido |
| Decisión al titular | Destinatario = titular y solicitud visible para su actor; no exige decidir |

Una identidad con consulta propia o global puede leer decisiones de sus propias
solicitudes si conserva acceso; la consulta global no permite leer avisos de otros
usuarios. Staff/superusuario y administración de cuentas no conceden acceso por sí
solos. La exclusión del autor de solicitud del primer evento NO se aplica al aviso
de decisión, cuyo destinatario es precisamente ese titular.

Bandeja, contador, marcado y envío/reintento aplican la misma matriz por tipo.
Tipos desconocidos se excluyen. Identidad no operativa o pérdida de visibilidad
impide acceder y genera Omitido si existe una intención que se intenta enviar.
Dirección inválida queda Fallido según SPEC-029. Volver a conceder acceso no envía
correos automáticamente ni crea una campaña histórica.

## Contenido y recorrido

- Aviso web: **Decisión registrada: Aceptada / Postergada / Rechazada**, número de
  solicitud y fecha de esa decisión. La fecha del evento se distingue de la de
  recepción si un aviso se recupera posteriormente.
- Correo individual, texto y HTML: asunto `[PS_Cooperadora] Decisión sobre solicitud
  de gasto #N`; número, resultado y fecha del evento, botón **Ver solicitud** y
  enlace alternativo. El motivo se consulta sólo en el detalle protegido; no se
  incluyen concepto, importes, datos bancarios, adjuntos ni direcciones de terceros.
- La redacción comunica un hecho histórico: «El ... se registró la decisión ...».
  Una postergación antigua no se presenta como estado actual si luego se aceptó.
  El enlace muestra el detalle e historial vigentes, sin afirmar requisitos nuevos
  o que aceptar equivalga a pagar. No se suprimen hechos previos por otro posterior.
- Abrir el enlace no marca leído ni decide. Se conserva marcado individual por
  POST con CSRF, timestamp estable ante repetición, filtros y paginación de 25.
- Reutilizar composición de la bandeja y plantilla existentes según la
  [guía visual](../visual-guide/README.md). El acceso **Avisos** y su contador se
  habilitan también para actores con consulta de Gastos, filtrando cada evento por
  su autorización; un lector puede encontrar una bandeja vacía. Esto amplía el
  acceso a la bandeja respecto de SPEC-028, sin darle avisos de operadores.
- Conservar la consulta única del contador al cargar, sin sondeo periódico ni
  consultas globales nuevas durante el renderizado de otras vistas.

## Correo y recuperación

Reutilizar `IntencionCorreo`, estados, exclusión PostgreSQL, URL validada, remitente
y activación explícita de SPEC-029. Crear intención junto con un aviso nuevo sólo
si `AVISOS_EMAIL_ENABLED=True`; enviar tras confirmar ambos. No reenviar aceptados
ni tomar inciertos/en proceso en reintentos normales. Conciliación explícita y
protección de emisor activo conservan sus garantías.

Extender el comando de correo por solicitud a los dos tipos reconocidos con
autorización específica por evento y sin crear intenciones históricas. Incorporar
recuperación web explícita por ID de decisión: deduplica y no prepara/envía correo.
El comando `reintentar_aviso_gasto` conserva su alcance de nueva solicitud web.
La guía explicará los comandos efectivos al implementar, sin otra consola web.

## Verificación y entrega

Revisión de Gemini sobre el plan antes de editar código. Luego dos incrementos:
productor/persistencia/permisos/recuperación; presentación/plantilla y guía.

Probar tres resultados válidos, postergación seguida de aceptación o rechazo,
repetición del mismo evento, conflicto concurrente y rollback. Verificar titular,
identidades inactivas/no verificadas, pérdida de permisos, ID ajeno, CSRF, contador,
paginación y lectura independiente. Repetir autorización al enviar y reintentar;
comprobar fallo/reintento sin perder decisión y sin duplicar hechos.

Regresión obligatoria del evento nueva solicitud: operadores siguen recibiendo
sus avisos/correos, solicitantes no ven esos avisos y comandos existentes conservan
sus efectos. QA Desktop/Mailpit prueba decisiones reales, mensaje histórico y
enlace protegido en escritorio y móvil. Distinguir pruebas automáticas, navegador,
HTTP, BD y simulación SMTP; registrar versión y límites en la PR. Publicar commits
coherentes; no declarar cierre con esta especificación ni con CI solamente.
