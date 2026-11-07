# SPEC-019 — Corrección de datos de cobros

- Estado: alcance ampliado por Matías el 06/11/2026; implementación para revisión.
- Issue: [#87](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/87).
- Responsable principal: Matías Alejandro Fernández.
- Rol de Franco Damián Sánchez: revisión de contratos y efectos compartidos.
- Validador: Matías para el alcance solicitado; Cooperadora para regularizaciones futuras.

## Problema y valor

El titular y Cooperadora necesitan corregir los datos manuales de un cobro
y conservar los registros de la carga, la revisión y la verificación previas.

## Alcance

### Incluye

Fecha, medio, operación, importe y documento de respaldo de cobros vigentes en
solicitudes abiertas. El titular puede corregir cobros que informó originalmente.
Cooperadora puede corregir los cobros que tiene autorización para gestionar.
La corrección exige un motivo y, en cobros confirmados, un cambio en los datos
manuales. La acción **Modificar cobro** reúne la corrección de datos y el
cambio del documento vinculado. Cambiar sólo el documento de un ingreso
confirmado conserva la verificación y requiere los permisos de actualización
documental. El titular puede presentar otro documento en un cobro pendiente
o rechazado para que Cooperadora revise el sucesor.
Un cobro rectificado ofrece la corrección en su ficha como acción opcional.

### No incluye

Correcciones en trámites terminales, devoluciones o movimientos de dinero.

## Requisitos verificables

- `CCO-R01`: autorización en servidor según visibilidad, estado y capacidades.
  El titular requiere informar e incorporar, y la autoría del cobro original.
  Cooperadora requiere registrar e incorporar, y también verificar para
  corregir un ingreso confirmado.
- `CCO-R02`: la corrección crea un sucesor y conserva datos, documento y
  verificación anteriores. Si el ingreso estaba confirmado, se registra su
  rectificación con el actor y motivo de la corrección antes de sustituirlo.
  Un cobro ya rectificado puede tener un sucesor sin duplicar la rectificación.
- `CCO-R03`: el sucesor queda pendiente de revisión documental y verificación
  de ingreso. Su documento puede incorporar un archivo nuevo o conservar el
  contenido vinculado o seleccionado en una nueva versión, sin trasladar
  la aceptación anterior.
- `CCO-R04`: sólo la versión de cobro vigente cuenta en saldo, seguimiento,
  filtros y cierre. Mantener ordinal visible del cobro raíz y cadena histórica.
- `CCO-R05`: duplicados, reenvíos y concurrencia no crean dos sucesores, no
  dejan sustitución sin sucesor ni archivos parciales.

## Reglas de negocio

Unicidad de medio/operación entre cobros vigentes: una corrección puede conservar
la misma referencia. El historial conserva también referencias erróneas anteriores.
La declaración inicial puede rastrearse hasta el cobro original; la verificación
y saldo se resuelven con el sucesor vigente, sin exigir una declaración falsa
con la referencia anterior corregida.

La rectificación cuando corresponda, la sustitución y las nuevas versiones
documental y de cobro se registran en una transacción bajo bloqueo de la
cabecera común. Si el estado de ingreso cambió después de abrir el formulario,
la pantalla solicita recargar para conocer el efecto de la corrección.

Las guardas PostgreSQL exigen rectificación antes de sustituir un confirmado,
un sucesor válido al confirmar la transacción y la inmutabilidad de los datos
históricos. Los servicios verifican exclusivamente versiones vigentes.

## Criterios de aceptación

1. Un cobro rechazado corregido conserva importe, rechazo y documento originales,
   y presenta nuevo ingreso pendiente sin duplicar su importe en el saldo.
2. Corrección sin archivo genera nueva versión con el contenido previo;
   con archivo nuevo valida PDF/JPEG/PNG y tamaño vigente.
3. El titular puede corregir un cobro propio confirmado. Cooperadora puede
   corregir un confirmado con permiso de verificación. Un trámite ajeno o
   terminal y un reenvío al ID sustituido quedan fuera de la operación.
4. Dos correcciones simultáneas generan un sucesor y un conflicto. Un duplicado
   en otro cobro vigente no deja marca ni documento nuevo.
5. Después de revisar y confirmar el sucesor, filtros, diagnóstico y cierre
   utilizan su importe; eventos previos y corrección siguen consultables.
6. SQL directo no permite reescribir datos monetarios, ocultar un cobro sin
   sucesor ni confirmar una versión sustituida.

## Datos, permisos y sensibilidad

Datos sintéticos, sin bancos reales. Se conservan la autoría, el motivo y la
fecha de cada corrección, rectificación y verificación.

## Módulos e interfaces

Matías: facturación/cobros y consumo documental. Reutiliza almacenamiento privado,
versionado y compensación documental. La FK de cobro y sus verificaciones
históricas siguen identificando cada versión; el enlace reemplaza une la cadena.
Consultas operativas usan cobros vigentes; historial usa todas las versiones.
No cambia estados ni contratos de gastos.

## Estrategia de prueba y evidencia

PostgreSQL: migración desde 0014, preservación de datos, denegaciones HTTP/servicio,
saldo/filtro/cierre, duplicados, SQL y dos conexiones concurrentes. Verificar
rollback de archivo ante error y conservación de versiones. Evidencia y SHA en
la PR; datos sintéticos únicamente.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-11-02 | Solicitud y aclaración expresa de Matías | Corregir datos/respaldo de cobros propios pendientes o rechazados; proteger confirmados. | Versionar correcciones, volver a revisión y conservar historia. |
| 2026-11-06 | Ampliación confirmada por Matías | Habilitar la corrección para titular y Cooperadora, incluidos confirmados y rectificados. | Rectificar y sustituir en una operación si el ingreso estaba confirmado; revisar y verificar el sucesor. |
