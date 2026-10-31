# SPEC-014 — Administración de catálogos y capacidades operativas

- Estado: para validar matriz y catálogo exactos.
- Issue: [#77](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/77), [#85](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/85).
- Responsable principal: Matías Alejandro Fernández.
- Rol del compañero: Franco Damián Sánchez revisa contratos compartidos y mantiene gastos/pagos.
- Validador: Cooperadora para operación; equipo/Sistemas para interfaces según el tramo.

## Problema y valor

Cooperadora necesita cambiar opciones del formulario y acceder a reportes desde un perfil esporádico separado de la operación diaria (08:16–09:57). También pide excepciones temporales a impedimentos, cuyas reglas todavía no están cerradas (01:08:35–01:16:32).

## Alcance

### Incluye

Administración autorizada de los catálogos acordados y definición del perfil administrador. Un tramo separado acuerda la interfaz común para excepciones temporales.

### No incluye

Convertir staff/superusuario en autoridad implícita; motor genérico de políticas; implementar reglas de deuda de gastos o inventar plazos, umbrales y sanciones.

## Requisitos verificables

- `ADM-R01`: un administrador con capacidad explícita mantiene las opciones acordadas sin modificar código.
- `ADM-R02`: conservar referencias históricas al cambiar o retirar opciones; una opción no utilizable para nuevas altas no elimina trámites anteriores.
- `ADM-R03`: separar mantenimiento y reportes de la operación diaria; denegar escrituras sin capacidad también por petición directa.
- `ADM-R04`: antes de implementar excepciones, acordar con Franco sujeto, circuito, restricción, autoridad, motivo, inicio/fin, vencimiento y efecto sobre nuevas solicitudes y subsanaciones.

## Reglas de negocio

La necesidad de mantenimiento está confirmada; el catálogo exacto y su equivalencia con producto/servicio y centro de costo requieren precisar. Modelo de retiro y auditoría son propuesta técnica para preservar trazabilidad. La deuda documental pertenece a gastos/Franco: una capacidad de administración no define cuándo bloquear. Cinco/diez días y cantidades de avisos son ejemplos de la conversación.

## Criterios de aceptación

1. El administrador autorizado cambia una opción y el formulario refleja el cambio; un operador sin esa facultad no puede hacerlo.
2. Trámites anteriores mantienen significado y referencias después de retirar una opción de nuevas altas.
3. La matriz explicita quién mantiene catálogos y consulta reportes, sin otorgar escritura por ser lector global.
4. Para el tramo de excepciones existe contrato revisado con Franco y casos sintéticos de ventana vigente/vencida y denegación; no se declara implementación por documentarlo.

## Datos, permisos y sensibilidad

Acciones con capacidades explícitas y autorización por objeto en servidor. Datos sintéticos o anonimizados para pruebas; fuentes originales privadas. No copiar datos personales, credenciales, respuestas ni audio a GitHub.

## Módulos e interfaces

Matías mantiene catálogos de facturación, identidad y capacidades comunes. Franco mantiene reglas/consumidor de gastos y revisa el contrato antes de integrarlo. Reportes: SPEC-008/#30.

## Estrategia de prueba y evidencia

Autorización de mantenimiento, entradas inválidas, preservación histórica y migración de opciones actuales; pruebas de contrato del tramo de excepciones una vez acordado. La entrega debe enlazar SHA, revisión y resultados realmente ejecutados; esta especificación no acredita nuevas pruebas ni implementación.

## Preguntas abiertas

Catálogos editables exactos, campos y retiro; cargos y asignación del perfil; alcance por persona/área/correo; política de vencimiento, bloqueo y excepciones; si aplica a ambos circuitos y en qué condiciones.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-10-29 | Demo; síntesis en [acta](../evidence/demo-2026-10-29.md) | Necesidad y límites descritos arriba. Los detalles abiertos no se consideran acordados. | Seguimiento propio, sin reabrir entregas técnicas históricas por ampliación. |

Fuente: demo de Cooperadora del 29/10/2026, audio y dos transcripciones locales en `docs/fuentes/Demo/`. Matías identificó el 31/10/2026 la versión demostrada: `09095a6d472bfcceeab21a4b371c7880f35e98c4`. Las transcripciones corresponden al mismo audio. No se publica el audio ni su contenido incidental. Registro operativo y síntesis de evidencia: #29.
