# Instrucciones compartidas para agentes

- Leer `CONTRIBUTING.md`, `docs/WORKFLOW.md` y `docs/QUALITY.md`; después, la Issue activa y sus especificaciones/contratos. Inspeccionar Git antes de editar y preservar trabajo existente.
- Aplicar `docs/QUALITY.md` al cambio concreto: elegir la solución más sencilla que cubra los escenarios acordados y justificar mecanismos adicionales por su beneficio y costo. La entrega identifica versión, verificaciones y límites.
- Mantener Django modular, PostgreSQL y plantillas Django. Franco mantiene gastos/pagos; Matías, facturación/cobros e identidad/documentos según las specs. Acordar interfaces antes de consolidar sus dependencias.
- H1–H4 siguen siendo hipótesis de demo mientras no haya validación registrada. No implementar SSO, ejecución de pagos, facturación externa o reglas institucionales por anticipación.
- Un implementador escribe código por checkout; el revisor inspecciona y verifica sin reimplementar ni escribir simultáneamente. No duplicar implementaciones del mismo componente.
- Trabajar en rama de tarea. Commits, publicación, push y merge siguen la autorización vigente; no descartar cambios ajenos.
- Revisar diff y pruebas por comportamiento/riesgo. Separar defectos materiales de mejoras opcionales; comprobar la coherencia del recorrido con los componentes visuales existentes, sin convertir la revisión en un rediseño o auditoría global.
- Mantener una fuente por finalidad según `docs/WORKFLOW.md`; actualizar la documentación afectada y el estado confirmado sin duplicar el seguimiento diario en specs y contratos. Redactar actividades, decisiones y resultados de forma neutral, conservando las contribuciones de cada responsable.
- Usar datos sintéticos. No mostrar ni versionar secretos, `.env`, bases, credenciales o respuestas reales de formularios.
- `.local/` es coordinación privada y no se versiona. No convertir rutas personales, herramientas particulares o preferencias de aprendizaje en dependencias del producto o reglas comunes.
- No se requieren skills nuevas para aplicar estos criterios. Los encargos a herramientas que no lean automáticamente este archivo deben exigir su lectura y la de `docs/QUALITY.md` antes de comenzar.
- Cada integrante elige herramientas, modelos y organización. Estas instrucciones no exigen orquestación, múltiples agentes ni el flujo particular de otro integrante.
