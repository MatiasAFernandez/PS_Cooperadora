# SPEC-024 — Edición administrativa de datos básicos locales

- Estado: alcance autorizado; implementación, revisión y prueba visual pendientes.
- Issue: [#117](https://github.com/MatiasAFernandez/PS_Cooperadora/issues/117).
- Responsable del alcance administrativo: Franco Damián Sánchez. Matías Alejandro Fernández conserva responsabilidad sobre identidad; su conformidad no se presume.
- Extiende la ficha de [SPEC-023](023-franco-consulta-usuarios-locales.md), sin cambiar el contrato de Actor.

## Recorrido y autorización

Desde la ficha, «Editar datos» abre un formulario con nombre completo, área habitual, CUIT / CUIL y legajo. «Guardar cambios» y «Cancelar» regresan a la ficha conservando filtros del listado. Sólo un actor con `identidad.administrar_cuentas` puede consultar o enviar el formulario. Se comprueba la autorización en servidor; staff/superusuario sin la capacidad no tienen acceso implícito. La bandera local desactivada responde 404. Se conserva CSRF y no-store.

Correo, clave, grupos, permisos, aprobación, verificación y actividad no son editables mediante este formulario, incluso si se agregan al POST. El nombre completo pertenece a CuentaLocal; no se modifica automáticamente el perfil legado de User ni la identidad histórica.

## Validación y persistencia

- Nombre obligatorio de hasta 150 caracteres; área opcional hasta 150; CUIT / CUIL opcional hasta 20; legajo opcional hasta 50. Se eliminan espacios exteriores, conforme a los límites actuales del alta. No se incorpora una regla institucional nueva de identificación fiscal.
- Errores de servidor visibles junto al campo, conservación de datos y cancelación sin escrituras. El envío idéntico no crea eventos.
- El guardado usa una transacción y bloqueo de la cuenta: modificación y evento de cambio se confirman juntos o se revierten juntos.
- Una referencia firmada a los valores originales identifica un formulario obsoleto. Se contrasta bajo bloqueo; si cambió la cuenta, no se sobrescribe y se explica cómo recargarla. No requiere un contador de revisión ni una plataforma de eventos.
- El evento registra cuenta, autor, fecha y sólo los valores anteriores/nuevos de los campos que cambiaron. No guarda POST completos, tokens, correos, credenciales ni datos bancarios.
- Historial paginado de 10 eventos en la ficha, ordenado por fecha e identificador descendentes, con etiquetas comprensibles. El flujo de aplicación sólo agrega eventos; no se afirma protección frente a escrituras SQL directas.

## Diseño y aceptación

Reutilizar ficha, formulario y estilos del módulo de usuarios y la [guía visual](../visual-guide/README.md), sin rediseñar el listado. Campos excluidos permanecen de consulta; el historial se presenta en una sección separada. Probar escritorio y móvil de 390 px, teclado, errores y retorno conservando filtros.

Pruebas pertinentes: guardado e historia, no-op, campos inválidos, POST manipulado, GET/POST sin facultad, CSRF, ficha inexistente, fallo al crear historia con rollback y formulario obsoleto. La migración es aditiva; no cambia registros previos. La revisión de navegador se documenta por separado de las pruebas HTTP.

Alta administrativa, perfiles, actividad, cambio de correo y borrado son hitos separados. No se introduce un motor genérico de auditoría ni se alteran reglas de Gastos o Facturación.
