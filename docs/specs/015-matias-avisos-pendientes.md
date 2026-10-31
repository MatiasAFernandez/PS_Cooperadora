# SPEC-015 — Avisos y acceso a pendientes

- Estado: para validar eventos y destinatarios; necesidad confirmada.
- Issue: [#78](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/78).
- Responsable principal: Matías Alejandro Fernández.
- Rol del compañero: Franco Damián Sánchez revisa contratos compartidos y mantiene gastos/pagos.
- Validador: Cooperadora para operación; equipo/Sistemas para interfaces según el tramo.

## Problema y valor

Una solicitud nueva u observada puede pasar días sin atención si el usuario no entra al detalle. Cooperadora pide avisos por correo y un acceso visible a pendientes (19:36–20:56; 01:28:42–01:29:27).

## Alcance

### Incluye

Aviso a Cooperadora por solicitud nueva de facturación; aviso al titular por observación/cambio que requiere acción; acceso inicial a sus pendientes. Contrato mínimo compartido para futuros eventos de gastos.

### No incluye

Enviar correos durante este trabajo documental; implementar deuda/bloqueos; emisión fiscal; asumir entrega del correo como aceptación. Envío de documentos de pagos/proveedor requiere el contrato de Franco.

## Requisitos verificables

- `AVI-R01`: generar avisos sólo por hechos persistidos y destinatarios configurados/autorizados.
- `AVI-R02`: mostrar al titular sus observaciones y pendientes mediante acceso directo desde inicio, sin revelar trámites ajenos.
- `AVI-R03`: una reentrega o reenvío HTTP no crea avisos indistinguibles duplicados; un fallo de correo no pierde la solicitud ni finge entrega.
- `AVI-R04`: acordar emisor, destinatarios, eventos, contenido mínimo y vínculo protegido antes de activar envíos reales.

## Reglas de negocio

El receptor administrativo será configurable; no publicar direcciones reales. Correo de agrupación, destinatario de factura y actor titular son conceptos distintos. La implementación elegirá el mecanismo más sencillo que cubra persistencia y fallo sin imponer infraestructura anticipada.

## Criterios de aceptación

1. Una solicitud válida deja el hecho de aviso correspondiente; una fallida no notifica una solicitud inexistente.
2. El titular accede desde su panel a la observación; otro usuario no obtiene el trámite ni por enlace directo.
3. Un fallo/reintento tiene resultado observable y no revierte el trámite ni declara entrega no comprobada.
4. El caso administrativo y el del titular se verifican con correo simulado y datos sintéticos.

## Datos, permisos y sensibilidad

Acciones con capacidades explícitas y autorización por objeto en servidor. Datos sintéticos o anonimizados para pruebas; fuentes originales privadas. No copiar datos personales, credenciales, respuestas ni audio a GitHub.

## Módulos e interfaces

Matías: facturación y mecanismo común mínimo. Franco: eventos, adjuntos y destinatarios de gastos/pagos. Identidad entrega titular; cada módulo determina pendientes y permisos.

## Estrategia de prueba y evidencia

Correo simulado, acceso por objeto, reenvíos, fallo/reintento y preservación del trámite. No usar datos ni buzones reales en pruebas. La entrega debe enlazar SHA, revisión y resultados realmente ejecutados; esta especificación no acredita nuevas pruebas ni implementación.

## Preguntas abiertas

Eventos de corrección/cobro/cierre que notifican; direcciones/emisor; adjunto o vínculo; tratamiento de reintentos; alcance del envío al proveedor solicitado en gastos.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-10-29 | Demo; síntesis en [acta](../evidence/demo-2026-10-29.md) | Necesidad y límites descritos arriba. Los detalles abiertos no se consideran acordados. | Seguimiento propio, sin reabrir entregas técnicas históricas por ampliación. |

Fuente: demo de Cooperadora del 29/10/2026, audio y dos transcripciones locales en `docs/fuentes/Demo/`. Matías confirmó el 31/10/2026 que el proyecto no cambió desde la demo: versión `09095a6d472bfcceeab21a4b371c7880f35e98c4`. Las transcripciones corresponden al mismo audio. No se publica el audio ni su contenido incidental. Registro operativo y síntesis de evidencia: #29.
