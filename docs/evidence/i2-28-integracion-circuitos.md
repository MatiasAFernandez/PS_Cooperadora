# Integración cruzada de gastos y facturación — #28

Base del corte inicial: `7fda5ce` (PR #68 integrada). Base del recorrido ampliado:
`4aadda7` (#65 y #66 integradas por Franco). Rama:
`codex/28-integracion-circuitos`. Aporte principal de Matías con asistencia de
Codex; revisión de contratos comunes y recorrido de gastos a cargo de Franco.
El estado operativo se mantiene en #28 y en su PR; este corte no declara la
aceptación institucional de #29 ni el cierre de #50.

## Cobertura y responsabilidades

| Requisito | Evidencia en este corte | Responsable / revisión |
|---|---|---|
| INT-R01 | Sesiones reales A/B/O/L, accesos ajenos 404, lector global sin escritura ni metadatos; revocación de pago no revoca facturación. | Identidad común: Matías; políticas de gasto: Franco. |
| INT-R02 | Documento de gasto y factura/cobro de facturación con cabecera correcta; descarga autorizada con bytes sintéticos; lectura/aporte ajenos denegados. | Documentos: Matías; consumo C01 y UI de gastos: Franco. |
| INT-R03 | Relación documental cruzada rechazada por PostgreSQL; rollback sin cambiar vínculo; aporte ajeno sin fila ni archivo adicional. | Cabecera/documentos: Matías; vínculos propios de gasto: Franco. |
| INT-R04 | Detalles HTTP con decisión/pago/aporte/revisión documental en gastos y presentación/comprobante/cobro/verificación/cierre en facturación; cada DTO conserva referencia, actor y fecha. | Contrato común/facturación: Matías; proyección de gasto: Franco. |
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
   O acepta con versión vigente; A abre desde el detalle la pantalla de carga de
   respaldo e incorpora una factura de proveedor sintética;
   O registra aceptación documental y pago externo usando la referencia de la
   versión exacta ofrecida por C01. Reenviar el mismo pago conserva un solo pago
   y evento. A reemplaza el documento desde la misma pantalla: v1 conserva su
   revisión y bytes; v2 queda vigente y pendiente, sin heredar aceptación. El
   pago sigue ligado a v1 y su reenvío no duplica eventos. El detalle muestra las
   dos versiones y los hechos documentales, sin inferir categoría vigente del
   respaldo pagado. El gasto permanece `aceptada`; el pago no es otra decisión.
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

El corte inicial `0649deb` aportaba al gasto por `POST documentos:tramite` (JSON).
El recorrido ampliado usa `gastos:documentos`, la pantalla de carga y reemplazo
entregada por Franco en #66, y la proyección documental de #65 en el detalle.
Se verifica por HTTP/renderizado, sin atribuirle inspección visual interactiva.

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

Franco aprobó el aporte inicial `0649deb` tras ejecutar 108 pruebas sobre una
combinación local con `4aadda7`; esa aprobación no comprendía este recorrido
ampliado ni el cierre de #28. Su observación sobre cuatro fallos de fixtures al
invocar sólo los dos módulos focales se reprodujo: la secuencia de gastos podía
entregar un número ya ocupado por la colisión pública intencional del fixture
común. La fábrica sintética ahora descarta los números ocupados, sin reiniciar
las secuencias ni modificar restricciones o servicios productivos. Los 17 casos de
esos dos módulos pasan juntos después del ajuste.

Validación local del recorrido ampliado: 17 pruebas focales en 9,73 s y 108
pruebas de integración/navegación en 36,21 s; Ruff y controles de Django y
migraciones aprobados. Conjuntos solapados, no se suman.

## Pendientes para el cierre conjunto

- #65/#66 ya están incorporadas por su dueño; la rama incluye `4aadda7`. Matías
  verificó su consumo desde el recorrido cruzado: pertenencia, historial por
  versión, carga/reemplazo y preservación del pago frente al cierre de facturación.
- Falta revisión de Franco del delta ampliado y su evidencia sobre el nuevo SHA,
  e integración de #69. Mantener #28 abierta hasta completar esos pasos; la
  aprobación inicial no se presenta como aceptación del cierre conjunto.
- La demostración/aceptación con Cooperadora y #29/#50 tienen seguimiento propio.
  No se activan reglas institucionales, almacenamiento compartido ni movimientos
  de dinero a partir de estas pruebas.
