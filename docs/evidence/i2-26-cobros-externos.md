# Verificación de #26 — ingresos externos

Fecha: 22/10/2026. Base: `f6448530c87a5a3b62f16ba3f19dc1df9047876c`.
Rama: `codex/26-cobros-externos`. Implementación principal de Matías con
asistencia de Codex. Perfil provisional confirmado por Matías: ARS, parciales y
anticipos por solicitud, identidad global medio/cuenta + operación, respaldo
nuevo/existente y verificación de ingreso independiente. No es validación institucional.

## Comportamiento y diseño

CobroExterno es un hecho propio inmutable. La solicitud protegida lo relaciona
con su factura única al existir, sin FK anulable ni actualización posterior de
anticipos. VerificacionCobro es un hecho único separado; PENDIENTE es ausencia
de verificación. El registro de ingreso es independiente de RevisionDocumento.
Ambos hechos se proyectan al DTO común; no se introducen estados de solicitud
ni cambios en gastos/pagos de Franco.

El alta reutiliza operacion_documental para compensación/recuperación de archivos;
no crea otro subsistema. Seleccionar el comprobante inicial fija su versión sin
copiar bytes ni tomar importe solicitado como recibido. La unicidad global,
pertenencia, importes finitos, ARS y conservación se protegen en SQL. Los servicios
controlan acción/objeto y serializan verificación; una segunda verificación da 409.

## Casos automatizados

`tests/facturacion/test_cobros.py` usa PostgreSQL real y archivos/cuentas sintéticas:

- Anticipos, dos parciales con centavos, factura posterior, confirmado/rechazado,
  cronología y estado/versiones de solicitud conservados.
- Reutilización del respaldo inicial sin copia; su declaración no crea ingresos.
- Rechazo de importes inválidos, cuenta corriente, operación vacía y fecha inválida.
- Capacidades independientes, CSRF real, revocación por petición y descarga ajena.
- Unicidad global, documento ajeno y concurrencia de dos solicitudes con misma
  operación: una sola alta y compensación del archivo perdedor.
- Fallos posteriores al alta o verificación: rollback sin hechos parciales.
- SQL rechaza vínculos ajenos, NaN, motivos sólo whitespace y UPDATE/DELETE.
- Dos verificadores concurrentes dejan un único hecho. Reversa con cobros se
  bloquea; reversa vacía/upgrade conserva la solicitud y su historial.
- Formulario 409 conserva los campos y avisa que debe seleccionarse de nuevo el archivo.

Las pantallas se renderizan mediante HTTP; no se declara inspección visual
interactiva. El [recorrido](../guides/recorrido-facturacion-i2.md) permite reproducir
la demo. La revisión cruzada de Franco se registra en la PR.

## Verificaciones ejecutadas

Python 3.14.7, Django 5.2.17 y PostgreSQL 18.6 aislado en loopback, con datos y
storage temporales sintéticos. No se alteró el checkout original ni ramas de Franco.

| Comprobación | Resultado |
|---|---|
| Conjunto focal de cobros | 22 passed in 18.53s |
| Suite completa | 552 passed in 202.90s |
| Ruff y diff --check | Aprobados |
| Django check | Sin incidencias |
| makemigrations --check --dry-run | Sin cambios |
| migrate | 0008/0009 aplicadas sobre la base anterior de solicitudes/comprobantes |

La suite incluye migración desde el esquema completo, reversa vacía y upgrade.
La CI de la PR verifica su commit final; no se suman conjuntos solapados.

## Límites del corte

No hay conciliación automática, movimiento de fondos, moneda extranjera,
descuentos/retenciones/comisiones ni corrección/anulación de registros o
verificaciones. Rechazar conserva identidad global y respaldo. Los registros
son definitivos para este corte; no se deben inventar referencias para corregirlos.
La cancelación/cierre pertenece a #27; el confirmado no prueba conformidad del PDF.
