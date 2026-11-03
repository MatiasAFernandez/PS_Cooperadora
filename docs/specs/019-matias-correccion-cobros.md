# SPEC-019 — Corrección de cobros informados por el titular

- Estado: alcance confirmado por Matías el 02/11/2026; implementación para revisión.
- Issue: [#87](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/87).
- Responsable principal: Matías Alejandro Fernández.
- Rol de Franco Damián Sánchez: revisión de contratos y efectos compartidos.
- Validador: Matías para el alcance solicitado; Cooperadora para regularizaciones futuras.

## Problema y valor

El titular necesita corregir cobros mal cargados, además de consultar el estado
de su solicitud. El importe o respaldo erróneo no debe perder su historia ni
alterar un ingreso ya confirmado.

## Alcance

### Incluye

Fecha, medio, operación, importe y respaldo de cobros cargados por el propio
titular, en solicitudes abiertas, cuyo ingreso está pendiente o rechazado.
Motivo explícito de corrección. Pantalla, botones y acceso desde atención.

### No incluye

Modificar cobros confirmados, cobros cargados por otra persona, ingresos de
otra solicitud ni trámites terminales. No ejecuta dinero ni anula ingresos.

## Requisitos verificables

- `CCO-R01`: autorización de titular, autor y capacidad informar/incorporar en
  servidor, con denegación por objeto y estado.
- `CCO-R02`: la corrección crea un sucesor y conserva datos, documento y
  verificación anteriores. El original sólo recibe una marca de sustitución,
  sin editar importe, medio, fecha, actor, documento ni operación.
- `CCO-R03`: el sucesor queda pendiente de revisión documental y verificación
  de ingreso. Si no se adjunta archivo nuevo se conserva el contenido mediante
  una nueva versión documental, sin trasladar la aceptación anterior.
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

La sustitución, nueva versión documental y cobro sucesor se realizan bajo bloqueo
de la cabecera común. Verificar ingreso y corregir compiten bajo el mismo bloqueo;
un cobro confirmado antes del bloqueo no puede corregirse. Los servicios de
Cooperadora siguen verificando exclusivamente versiones vigentes.

Las guardas PostgreSQL sólo permiten marcar como sustituido un cobro del
solicitante no confirmado y sin cambiar otros campos. Exigen sucesor válido al
commit; no permiten verificar un cobro sustituido. No se borra historia para
corregir. La reversa rechaza eliminar el esquema si ya existen correcciones.

## Criterios de aceptación

1. Un cobro rechazado corregido conserva importe, rechazo y documento originales,
   y presenta nuevo ingreso pendiente sin duplicar su importe en el saldo.
2. Corrección sin archivo genera nueva versión con el contenido previo;
   con archivo nuevo valida PDF/JPEG/PNG y tamaño vigente.
3. Confirmado, ajeno, terminal o cargado por otro actor se deniega; GET y POST
   aplican las mismas facultades. Un reenvío al ID sustituido no crea otro cobro.
4. Dos correcciones simultáneas generan un sucesor y un conflicto. Un duplicado
   en otro cobro vigente no deja marca ni documento nuevo.
5. Después de revisar y confirmar el sucesor, filtros, diagnóstico y cierre
   utilizan su importe; eventos previos y corrección siguen consultables.
6. SQL directo no permite reescribir datos monetarios, ocultar un cobro sin
   sucesor ni confirmar una versión sustituida.

## Datos, permisos y sensibilidad

Datos sintéticos, sin bancos reales. Reutiliza facturacion.informar_cobro y
documentos.incorporar; exige titularidad y autoría además de la capacidad.
Cooperadora no recibe facultades nuevas sobre sus propios registros por este flujo.

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

## Preguntas abiertas

La regularización de ingresos ya confirmados queda fuera de este alcance y
requiere un flujo operativo independiente.

## Decisiones

| Fecha | Fuente | Decisión | Consecuencia |
|---|---|---|---|
| 2026-11-02 | Solicitud y aclaración expresa de Matías | Corregir datos/respaldo de cobros propios pendientes o rechazados; proteger confirmados. | Versionar correcciones, volver a revisión y conservar historia. |
