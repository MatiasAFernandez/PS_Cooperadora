# Integración cruzada de gastos y facturación — #28

Base verificada: `7fda5ce` (PR #68 integrada). Rama:
`codex/28-integracion-circuitos`. Aporte principal de Matías con asistencia de
Codex; revisión de contratos comunes y recorrido de gastos a cargo de Franco.
El estado operativo se mantiene en #28 y en su PR; este corte no declara la
aceptación institucional de #29 ni completa las entregas de gastos pendientes.

## Cobertura y responsabilidades

| Requisito | Evidencia en este corte | Responsable / revisión |
|---|---|---|
| INT-R01 | Sesiones reales A/B/O/L, accesos ajenos 404, lector global sin escritura ni metadatos; revocación de pago no revoca facturación. | Identidad común: Matías; políticas de gasto: Franco. |
| INT-R02 | Documento de gasto y factura/cobro de facturación con cabecera correcta; descarga autorizada con bytes sintéticos; lectura/aporte ajenos denegados. | Documentos: Matías; consumo C01 y UI de gastos: Franco. |
| INT-R03 | Relación documental cruzada rechazada por PostgreSQL; rollback sin cambiar vínculo; aporte ajeno sin fila ni archivo adicional. | Cabecera/documentos: Matías; vínculos propios de gasto: Franco. |
| INT-R04 | Detalles HTTP con eventos de decisión/pago y presentación/comprobante/cobro/verificación/cierre; cada DTO conserva referencia, actor y fecha. | Contrato común/facturación: Matías; proyección de gasto: Franco. |
| INT-R05 | Inicio común -> ambos listados -> presentación -> detalle; pago y cierre explícitos en una misma base sin mezclar estados. | Navegación común: Franco; integración de facturación: Matías. |

`tests/integracion/test_issue_28_recorridos.py` ejecuta cinco casos sobre
PostgreSQL real. No simula el proveedor ni los servicios de identidad. Usa el
cliente HTTP de Django con sesiones autenticadas y cuentas sintéticas; no es
una inspección visual del navegador ni una nueva prueba de CSRF. Las pruebas de
contratos, versiones, concurrencia y pagos ya existentes se ejecutan junto a él.

## Dos recorridos sintéticos reproducibles

Preparar una base PostgreSQL y almacenamiento **aislados**, aplicar migraciones
y habilitar `DEMO_IDENTITY_ENABLED` sólo en la demo. Configurar explícitamente:

```text
GASTOS_PAYMENT_DOCUMENT_PROVIDER=documentos.c01.ProveedorDocumentalGastos
```

Crear los perfiles con:

```console
python manage.py preparar_identidad_demo --facturacion --revision-documental --verificacion-cobros --resolucion-facturacion
```

Las cuentas nuevas no tienen contraseña utilizable; asignarla localmente con
`changepassword` sin publicarla. El pago de gastos exige agregar explícitamente
`demo_gastos_pago` a O, además de consulta y metadatos. El comando no concede ese
grupo por decidir ni modifica el proveedor global. Los tests crean esa asignación
en su propia base efímera, sin alterar cuentas existentes.

1. **Gasto de A:** presentar necesidad por 100,25 ARS desde la navegación común;
   O acepta con versión vigente; A incorpora factura de proveedor sintética;
   O registra aceptación documental y pago externo usando la referencia de la
   versión exacta ofrecida por C01. Reenviar el mismo pago conserva un solo pago
   y evento. El gasto permanece `aceptada`; el pago no es otra decisión.
2. **Facturación de B:** presentar datos para emitir por 100,25 ARS, sin declarar
   transferencia; O registra factura externa PDF; B informa cobro por ese importe;
   O confirma ingreso y acepta ambas versiones documentales. El trámite sigue
   `PRESENTADA` hasta que O cierra explícitamente con motivo y revisión vigente.
   Queda `CERRADA`, con historial y descarga autorizada; no modifica el gasto.
3. A no obtiene documentos de B y B no obtiene documentos de A, incluso por URL
   directa. L consulta ambos trámites pero no decide, resuelve ni obtiene
   metadatos documentales. Retirar a O `demo_gastos_pago` deniega pagar en la
   siguiente petición sin impedir registrar factura; retirar su perfil de
   facturación mantiene la consulta de gastos.

El aporte de gasto de este corte pasa por la interfaz HTTP documental compartida
`POST documentos:tramite`, que devuelve JSON. **No se presenta como una pantalla
de carga de gastos terminada.** La integración visual de carga/reemplazo y la
cronología documental del gasto corresponden a las PR #66 y #65 de Franco.
La revisión por versión se puede consultar en la pantalla del documento en main.

## Verificación

Con dependencias y las variables PostgreSQL apuntando a la base aislada:

```console
pytest tests/integracion tests/identidad/test_navegacion_comun.py -q
ruff check .
python manage.py check
python manage.py makemigrations --check --dry-run
```

La CI de la PR comprueba la suite completa sobre su SHA. Los resultados de este
corte y el enlace al run se registran en la PR, sin sumar conjuntos solapados.

## Pendientes para el cierre conjunto

- Franco debe integrar como dueño #65 y #66 después de sus revisiones. Este
  aporte no cambia sus ramas ni reproduce su implementación. Después se debe
  actualizar la rama de integración y comprobar historial por versión y
  carga/reemplazo desde el detalle de gastos, con permisos y proveedor real.
- Revisión cruzada de Franco sobre este diff y los ejemplos de gastos; revisión
  de Matías del consumo común tras integrar los heads finales de esas PR.
- Ejecutar la verificación conjunta sobre la versión integrada y registrar los
  resultados. Mantener #28 abierta mientras ese tramo no esté incorporado.
- La demostración/aceptación con Cooperadora y #29/#50 tienen seguimiento propio.
  No se activan reglas institucionales, almacenamiento compartido ni movimientos
  de dinero a partir de estas pruebas.
