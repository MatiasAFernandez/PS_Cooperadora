# SPEC-009 — Contratos e integración de los dos circuitos

- Estado: borrador; pendiente de revisión conjunta con Franco.
- Autor y responsable principal: Matías Alejandro Fernández por su aporte de
  estructura, identidad y documentos compartidos.
- Issue: pendiente de crear; dividir las integraciones verificables en tareas.
- Rol de Franco: acordar ejemplos de gastos, integrar su recorrido y revisar los
  contratos y cambios comunes.
- Validadores: Franco y Matías para interfaces; Cooperadora para el recorrido
  integrado; tutor técnico cuando afecte arquitectura institucional.
- Plan: I01-I05 y RF-001/RF-004/RF-006 compartidos.

## Problema y valor

Los módulos de gastos y facturación forman una sola aplicación. La identidad,
documentos, relaciones e historial deben comportarse de forma coherente para que
el usuario pueda seguir ambos circuitos y el equipo pueda integrarlos sin
duplicar reglas contradictorias.

## Alcance

### Incluye

- Acuerdo de identificadores, relaciones e integridad de datos compartidos.
- Contratos internos de identidad/permisos, documentos y eventos; pruebas de
  acceso e integridad en ambos circuitos.
- Adaptación de facturación a la navegación y presentación común de Franco.
- Escenarios de demostración integrados con datos sintéticos.

### No incluye

- Crear una API HTTP entre módulos ni servicios desplegados por separado.
- Redefinir la propiedad funcional de gastos/pagos de Franco.
- Integración directa con sistemas externos ni despliegue institucional.

## Requisitos verificables

- `INT-R01`: los dos módulos usan el contrato acordado de identidad y capacidades
  y deniegan accesos indebidos de la misma forma.
- `INT-R02`: documentos de ambos circuitos se vinculan a su trámite y se recuperan
  sólo mediante autorización comprobada.
- `INT-R03`: identificadores y relaciones compartidas impiden referencias
  huérfanas o cruzadas indebidamente.
- `INT-R04`: eventos de ambos circuitos presentan al menos tipo, actor y fecha;
  cada módulo conserva sus reglas de estado propias.
- `INT-R05`: el recorrido de facturación se puede demostrar desde la navegación
  común y sus operaciones no rompen el recorrido de gastos.

## Reglas de negocio

- Cada módulo mantiene la responsabilidad por sus decisiones y transiciones.
- Un contrato compartido se acuerda con ejemplos de ambos circuitos antes de
  cambiar modelos o interfaces que dependan de él.
- La integración se verifica con datos sintéticos y casos permitidos/denegados;
  la devolución de Cooperadora se registra por separado.

## Criterios de aceptación

1. Dadas identidades ficticias con capacidades distintas, cuando se recorren
   gastos y facturación, entonces las operaciones ajenas o no autorizadas se
   deniegan en ambos módulos.
2. Dado un documento de cada circuito, cuando se solicita por vínculo directo,
   entonces sólo el usuario autorizado obtiene el archivo correcto.
3. Dadas relaciones válidas e inválidas, cuando se ejecutan escenarios de ambos
   módulos, entonces las válidas persisten y las inválidas no dejan cambios parciales.

## Datos, permisos y sensibilidad

- Datos requeridos: identificadores de trámite, identidad, capacidades, enlaces
  documentales y eventos; esquema exacto pendiente de diseño conjunto.
- Roles autorizados: los establecidos por SPEC-002 y por cada módulo.
- Datos sintéticos o anonimizados para pruebas: un recorrido representativo de
  cada circuito, documentos ficticios y usuarios con permisos distintos.

## Módulos e interfaces

- Módulo propietario: componentes compartidos a cargo de Matías según el plan;
  navegación e historial visual común a cargo de Franco; contratos revisados por ambos.
- Entradas y salidas: identidad, trámite, documento y evento en interfaces Django
  internas, con errores y denegaciones acordados.
- Dependencias: SPEC-001 a SPEC-007 y decisiones de diseño de ambos alumnos.
- Integración requerida: I01 modelo, I02 permisos, I03 documentos, I04 navegación
  e I05 escenarios de integración.

## Estrategia de prueba y evidencia

- Pruebas unitarias: invariantes de identificadores y relaciones compartidas.
- Pruebas de integración: contratos y denegaciones cruzadas con PostgreSQL,
  recuperación documental y operaciones atómicas.
- Demostración o evidencia: dos recorridos completos, matriz de responsabilidades,
  resultados de pruebas y observaciones de Cooperadora.

## Preguntas abiertas

- ¿Qué datos y estados son realmente comunes y cuáles pertenecen a cada módulo?
- ¿Quién integra cada cambio compartido y quién revisa el contrato?
- ¿Qué navegación e historial visual requiere la demostración conjunta?
- ¿Qué ejemplos de ambos circuitos prueban la integridad antes de fijar el modelo?

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-09-17 | Plan de Trabajo corregido y división registrada en README | Una aplicación Django modular con propiedad vertical y componentes compartidos. | Los contratos se acuerdan con Franco antes de implementarlos. |
