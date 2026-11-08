(function () {
  const input = document.getElementById("id_monto_estimado");
  if (!input) return;

  const formatter = new Intl.NumberFormat("es-AR", {
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  });

  function parsearImporte(raw) {
    const s = raw.trim();
    if (!s) return null;
    if (/^\d+(?:[.,]\d{1,2})?$/.test(s)) {
      return Number(s.replace(",", "."));
    }
    if (/^\d{1,3}(?:\.\d{3})*,\d{1,2}$/.test(s)) {
      return Number(s.replace(/\./g, "").replace(",", "."));
    }
    if (/^\d{1,3}(?:,\d{3})*\.\d{1,2}$/.test(s)) {
      return Number(s.replace(/,/g, ""));
    }
    return null;
  }

  input.addEventListener("blur", function () {
    const numero = parsearImporte(input.value);
    if (numero !== null && Number.isFinite(numero) && numero > 0 && numero < 1e10) {
      input.value = formatter.format(numero);
    }
  });
})();
