(() => {
  "use strict";

  const root = document.querySelector(".registro-pago");
  if (!root) return;

  const form = root.querySelector("form[data-pago-form]");
  const maxBytes = Number(form?.dataset.maxBytes || 10 * 1024 * 1024);
  const modo = form?.dataset.mode || "alta";

  const $ = (id) => document.getElementById(id);
  const brutoInput = $("id_monto_bruto");
  const retencionInput = $("id_monto_retencion_atp");
  const fechaInput = $("id_fecha_pago");
  const netoInput = $("rp-neto");
  const errores = $("rp-errores");
  const avisoAtp = $("rp-aviso-atp");

  const estado = {
    banco: null,
    atp: null,
    sugerencia: null,
    baseEditada: false,
  };

  const RE_ASCII_SIN_SEPARADORES = /^[+-]?\d+(?:\.\d{1,2})?$/;
  const RE_ASCII_CON_MILES = /^[+-]?\d{1,3}(?:,\d{3})+\.\d{1,2}$/;
  const RE_ASCII_SOLO_MILES = /^[+-]?\d{1,3}(?:,\d{3}){2,}$/;
  const RE_ES_AR_SIN_MILES = /^[+-]?\d+,\d{1,2}$/;
  const RE_ES_AR_CON_MILES = /^[+-]?\d{1,3}(?:\.\d{3})+,\d{1,2}$/;
  const RE_ES_AR_SOLO_MILES = /^[+-]?\d{1,3}(?:\.\d{3}){2,}$/;

  function parseMoney(raw) {
    if (raw === null || raw === undefined) return null;
    let s = String(raw).trim();
    if (!s) return null;
    if (s.startsWith("$")) s = s.slice(1).trim();
    if (!s) return null;

    let normalized = null;
    if (RE_ASCII_SIN_SEPARADORES.test(s)) {
      normalized = s;
    } else if (RE_ASCII_CON_MILES.test(s) || RE_ASCII_SOLO_MILES.test(s)) {
      normalized = s.replace(/,/g, "");
    } else if (RE_ES_AR_SIN_MILES.test(s)) {
      normalized = s.replace(",", ".");
    } else if (RE_ES_AR_CON_MILES.test(s) || RE_ES_AR_SOLO_MILES.test(s)) {
      normalized = s.replace(/\./g, "").replace(",", ".");
    } else {
      return null;
    }

    if (normalized.startsWith("-")) return null;
    if (normalized.startsWith("+")) normalized = normalized.slice(1);
    if (!/^\d{1,10}(?:\.\d{1,2})?$/.test(normalized)) return null;

    const [entero, decimales = ""] = normalized.split(".");
    const centavos = Number(entero) * 100 + Number(decimales.padEnd(2, "0"));
    return Number.isSafeInteger(centavos) ? centavos : null;
  }

  const baseImponibleCentavos = parseMoney(form?.dataset.baseImponible) || 0;

  function formatMoneyEsAR(centavos) {
    if (centavos === null || isNaN(centavos)) return "";
    const n = centavos / 100;
    return n.toLocaleString("es-AR", {
      minimumFractionDigits: 2,
      maximumFractionDigits: 2,
    });
  }

  function money(centavos) {
    return centavos === null || isNaN(centavos) ? "—" : `$ ${formatMoneyEsAR(centavos)}`;
  }

  function canonico(raw) {
    const centavos = parseMoney(raw);
    return centavos === null ? String(raw ?? "") : (centavos / 100).toFixed(2);
  }

  function fechaLegible(valor) {
    if (!valor) return "—";
    const partes = String(valor).split("-");
    return partes.length === 3 ? `${partes[2]}/${partes[1]}/${partes[0]}` : valor;
  }

  function tamano(bytes) {
    if (!Number.isFinite(bytes) || bytes <= 0) return "tamaño no informado";
    if (bytes >= 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(1)} MiB`;
    return `${Math.max(1, Math.ceil(bytes / 1024))} KB`;
  }

  function setEstadoDocumento(kind, texto, esError) {
    const nodo = $(kind === "banco" ? "rp-banco-status" : "rp-atp-status");
    if (!nodo) return;
    nodo.hidden = !texto;
    nodo.textContent = texto || "";
    nodo.classList.toggle("rp-error", Boolean(esError));
  }

  function docElements(kind) {
    const prefijo = kind === "banco" ? "rp-banco" : "rp-atp";
    return {
      drop: $(`${prefijo}-drop`),
      card: $(`${prefijo}-file`),
      nombre: $(`${prefijo}-nombre`),
      meta: $(`${prefijo}-meta`),
      actions: $(`${prefijo}-actions`),
      abrir: $(`${prefijo}-abrir`),
      descargar: $(`${prefijo}-descargar`),
      cambiar: $(`${prefijo}-cambiar`),
      quitar: $(`${prefijo}-quitar`),
      input: $(kind === "banco" ? "id_comprobante_bancario" : "id_constancia_atp"),
      existing: $(`${prefijo}-existing`),
    };
  }

  function renderDocumento(kind) {
    const el = docElements(kind);
    if (!el.drop || !el.card) return;
    const actual = kind === "banco" ? estado.banco : estado.atp;
    if (actual) {
      el.drop.hidden = true;
      el.card.hidden = false;
      if (el.nombre) el.nombre.textContent = actual.nombre;
      if (el.meta) el.meta.textContent = tamano(actual.tamano);
      const url = actual.url || actual.openUrl || "";
      if (el.abrir) {
        el.abrir.href = url || "#";
        el.abrir.dataset.openUrl = actual.openUrl || "";
        el.abrir.dataset.openDoc = actual.openUrl || "";
        el.abrir.hidden = !url;
      }
      if (el.descargar) {
        el.descargar.href = actual.url || actual.downloadUrl || actual.openUrl || "#";
        el.descargar.download = actual.nombre;
        el.descargar.hidden = !(actual.url || actual.downloadUrl || actual.openUrl);
      }
      if (el.cambiar) el.cambiar.hidden = false;
      if (el.quitar) el.quitar.hidden = Boolean(actual.existing);
    } else {
      el.drop.hidden = false;
      el.card.hidden = true;
    }
    actualizarResumen();
  }

  function existenteDesdeHtml(kind) {
    const el = docElements(kind);
    if (!el.existing) return null;
    const nombre = el.existing.dataset.name;
    if (!nombre) return null;
    return {
      nombre,
      tamano: Number(el.existing.dataset.size || 0),
      openUrl: el.existing.dataset.openUrl || "",
      downloadUrl: el.existing.dataset.downloadUrl || "",
      existing: true,
    };
  }

  async function validarArchivo(kind, file) {
    if (!file) {
      return kind === "atp" ? "Seleccioná un archivo PDF." : "Seleccioná un comprobante (PDF o imagen).";
    }
    const lowerName = file.name.toLowerCase();
    if (file.size > maxBytes) {
      return `El archivo supera el máximo de ${(maxBytes / (1024 * 1024)).toFixed(0)} MiB.`;
    }
    if (file.size === 0) return "El archivo está vacío.";

    if (kind === "atp") {
      if (!lowerName.endsWith(".pdf")) return "La constancia ATP debe tener extensión .pdf.";
      try {
        const cabecera = new Uint8Array(await file.slice(0, 5).arrayBuffer());
        if (String.fromCharCode(...cabecera) !== "%PDF-") {
          return "El contenido no corresponde a un PDF válido.";
        }
      } catch (error) {
        return "No se pudo leer el archivo elegido.";
      }
      return null;
    }

    // Comprobante bancario: PDF, JPG, JPEG, PNG
    const esPdf = lowerName.endsWith(".pdf");
    const esJpg = lowerName.endsWith(".jpg") || lowerName.endsWith(".jpeg");
    const esPng = lowerName.endsWith(".png");
    if (!esPdf && !esJpg && !esPng) {
      return "El comprobante bancario debe ser un archivo PDF, JPG o PNG.";
    }

    try {
      const buffer = await file.slice(0, 8).arrayBuffer();
      const bytes = new Uint8Array(buffer);
      if (esPdf) {
        const magic = String.fromCharCode(...bytes.slice(0, 5));
        if (magic !== "%PDF-") return "El contenido no corresponde a un PDF válido.";
      } else if (esJpg) {
        if (bytes[0] !== 0xFF || bytes[1] !== 0xD8 || bytes[2] !== 0xFF) {
          return "El contenido no corresponde a una imagen JPEG válida.";
        }
      } else if (esPng) {
        const pngMagic = [0x89, 0x50, 0x4E, 0x47, 0x0D, 0x0A, 0x1A, 0x0A];
        for (let i = 0; i < pngMagic.length; i++) {
          if (bytes[i] !== pngMagic[i]) {
            return "El contenido no corresponde a una imagen PNG válida.";
          }
        }
      }
    } catch (error) {
      return "No se pudo leer el archivo elegido.";
    }
    return null;
  }

  async function aceptarArchivo(kind, file) {
    const anterior = kind === "banco" ? estado.banco : estado.atp;
    if (!file) return;
    const problema = await validarArchivo(kind, file);
    if (problema) {
      setEstadoDocumento(kind, problema, true);
      const input = docElements(kind).input;
      if (anterior && anterior.file && window.DataTransfer) {
        try {
          const dt = new DataTransfer();
          dt.items.add(anterior.file);
          input.files = dt.files;
        } catch (e) {
          input.value = "";
        }
      } else if (input) {
        input.value = "";
      }
      if (anterior) {
        renderDocumento(kind);
      }
      return;
    }
    const url = URL.createObjectURL(file);
    const nuevo = { nombre: file.name, tamano: file.size, url, file };
    if (anterior?.url && !anterior.existing) URL.revokeObjectURL(anterior.url);
    if (kind === "banco") estado.banco = nuevo;
    else estado.atp = nuevo;
    setEstadoDocumento(kind, "", false);
    renderDocumento(kind);
    sincronizarAvisoAlCorregir(kind);
  }

  function quitarArchivo(kind) {
    const actual = kind === "banco" ? estado.banco : estado.atp;
    if (actual?.url && !actual.existing) URL.revokeObjectURL(actual.url);
    if (kind === "banco") estado.banco = null;
    else estado.atp = null;
    const input = docElements(kind).input;
    if (input) input.value = "";
    renderDocumento(kind);
    sincronizarAvisoAlCorregir(kind);
  }

  function actualizarResumen() {
    if (modo !== "alta" && modo !== "rectificacion") return;
    const bruto = parseMoney(brutoInput?.value);
    const retencion = parseMoney(retencionInput?.value);

    const inlineError = $("rp-retencion-inline-error");
    let neto = null;
    if (bruto !== null && retencion !== null) {
      if (retencion >= bruto) {
        if (inlineError) {
          inlineError.hidden = false;
          inlineError.textContent = "La retención debe ser menor que el monto bruto.";
          inlineError.dataset.errorTipo = "logico";
        }
        if (retencionInput) {
          retencionInput.setAttribute("aria-invalid", "true");
          retencionInput.setAttribute("aria-describedby", "rp-retencion-inline-error");
        }
        neto = null;
      } else {
        if (inlineError && inlineError.dataset.errorTipo !== "formato") {
          inlineError.hidden = true;
          inlineError.textContent = "";
          delete inlineError.dataset.errorTipo;
          if (retencionInput) retencionInput.removeAttribute("aria-invalid");
        }
        neto = bruto - retencion;
      }
    } else {
      if (inlineError && inlineError.dataset.errorTipo === "logico") {
        inlineError.hidden = true;
        inlineError.textContent = "";
        delete inlineError.dataset.errorTipo;
        if (retencionInput) retencionInput.removeAttribute("aria-invalid");
      }
    }

    if (netoInput) {
      netoInput.value = neto === null ? "—" : money(neto);
    }
    const sum = (id, valor) => {
      const nodo = $(id);
      if (nodo) nodo.innerHTML = valor;
    };
    sum("rp-sum-fecha", fechaLegible(fechaInput?.value));
    sum("rp-sum-bruto", money(bruto));
    sum("rp-sum-retencion", money(retencion));
    sum("rp-sum-neto", neto === null ? "—" : money(neto));
    sum(
      "rp-sum-banco",
      estado.banco
        ? '<span class="rp-chip rp-chip-success">Seleccionado</span>'
        : '<span class="rp-chip rp-chip-warning">Falta adjuntar</span>'
    );

    const cardAtp = $("rp-atp-card");
    const uploadAtp = $("rp-atp-upload");
    const refAtpGroup = $("rp-atp-ref-group");
    const refAtpInput = $("id_referencia_atp");
    const atpFileInput = $("id_constancia_atp");
    const pendienteAtp = $("rp-atp-pending");
    const decision = document.querySelector('input[name="atp_decision"]:checked')?.value;

    if (retencion === null) {
      if (cardAtp) cardAtp.hidden = true;
      sum("rp-sum-atp", "Por definir");
    } else if (retencion === 0) {
      if (cardAtp) cardAtp.hidden = true;
      sum("rp-sum-atp", "No aplica");
    } else {
      if (cardAtp) cardAtp.hidden = false;
      const esDiferida = decision === "despues";
      if (refAtpGroup) refAtpGroup.hidden = esDiferida;
      if (uploadAtp) uploadAtp.hidden = esDiferida;
      if (pendienteAtp) pendienteAtp.hidden = !esDiferida;

      if (esDiferida) {
        if (estado.atp) {
          quitarArchivo("atp");
        }
        if (refAtpInput) {
          refAtpInput.value = "";
          refAtpInput.disabled = true;
        }
        if (atpFileInput) atpFileInput.disabled = true;
        sum("rp-sum-atp", '<span class="rp-chip rp-chip-warning">Constancia ATP pendiente</span>');
      } else {
        if (refAtpInput) refAtpInput.disabled = false;
        if (atpFileInput) atpFileInput.disabled = false;
        const adjunta = Boolean(estado.atp);
        sum(
          "rp-sum-atp",
          adjunta
            ? '<span class="rp-chip rp-chip-success">Seleccionado</span>'
            : '<span class="rp-chip rp-chip-warning">Falta adjuntar</span>'
        );
      }
    }

    const respaldoSelect = $("id_referencia_documental");
    if (!respaldoSelect || !respaldoSelect.options || respaldoSelect.options.length === 0) {
      sum("rp-sum-respaldo", '<span class="rp-chip rp-chip-warning">Falta cargar</span>');
    } else {
      const idx = respaldoSelect.selectedIndex >= 0 ? respaldoSelect.selectedIndex : 0;
      const opt = respaldoSelect.options[idx];
      const texto = opt ? opt.text : "";
      const sumEl = $("rp-sum-respaldo");
      if (sumEl) sumEl.textContent = texto;
    }

    if (avisoAtp) {
      const aplica = bruto !== null && baseImponibleCentavos > 0 && bruto >= baseImponibleCentavos;
      avisoAtp.hidden = !aplica;
    }
  }

  function invalidarSugerencia() {
    estado.sugerencia = null;
    const usar = $("rp-use");
    const resultado = $("rp-rate-result");
    if (usar) usar.hidden = true;
    if (resultado) {
      resultado.textContent = "";
      resultado.className = "rp-calc-feedback";
      resultado.hidden = true;
    }
  }

  function calcularPorcentaje() {
    const base = parseMoney($("rp-base")?.value);
    const tasaRaw = String($("rp-rate")?.value || "").trim().replace(",", ".");
    const resultado = $("rp-rate-result");
    const usar = $("rp-use");
    if (base === null || base <= 0 || !/^\d{1,3}(?:\.\d{1,4})?$/.test(tasaRaw)) {
      if (resultado) {
        resultado.className = "rp-calc-feedback rp-calc-warning";
        resultado.textContent = "Revisá la base y el porcentaje (0 a 100, hasta cuatro decimales).";
        resultado.hidden = false;
      }
      if (usar) usar.hidden = true;
      estado.sugerencia = null;
      return;
    }
    const [entero, decimales = ""] = tasaRaw.split(".");
    const tasaEscalada = BigInt(entero) * 10000n + BigInt(decimales.padEnd(4, "0"));
    if (tasaEscalada > 1000000n) {
      if (resultado) {
        resultado.className = "rp-calc-feedback rp-calc-warning";
        resultado.textContent = "El porcentaje debe estar entre 0 y 100.";
        resultado.hidden = false;
      }
      if (usar) usar.hidden = true;
      estado.sugerencia = null;
      return;
    }
    const sugerencia = Number((BigInt(base) * tasaEscalada + 500000n) / 1000000n);
    estado.sugerencia = sugerencia;
    if (resultado) {
      resultado.className = "rp-calc-feedback rp-calc-success";
      resultado.innerHTML = `Sugerencia aritmética: <strong>${money(sugerencia)}</strong>. Confirmá que coincida con ATP.`;
      resultado.hidden = false;
    }
    if (usar) usar.hidden = false;
  }

  function conectarDropzone(kind) {
    const el = docElements(kind);
    if (!el.input || !el.drop) return;
    el.input.addEventListener("change", (event) => {
      const file = event.target.files?.[0];
      if (file) aceptarArchivo(kind, file);
    });
    ["dragenter", "dragover"].forEach((evento) => {
      el.drop.addEventListener(evento, (event) => {
        event.preventDefault();
        el.drop.classList.add("is-over");
      });
    });
    ["dragleave", "dragend"].forEach((evento) => {
      el.drop.addEventListener(evento, () => el.drop.classList.remove("is-over"));
    });
    el.drop.addEventListener("drop", (event) => {
      event.preventDefault();
      el.drop.classList.remove("is-over");
      if (event.dataTransfer.files.length !== 1) {
        setEstadoDocumento(kind, "Elegí un único archivo.", true);
        return;
      }
      aceptarArchivo(kind, event.dataTransfer.files[0]);
    });
    if (el.cambiar) el.cambiar.addEventListener("click", () => el.input.click());
    if (el.quitar) el.quitar.addEventListener("click", () => quitarArchivo(kind));
    el.drop.addEventListener("click", (event) => {
      if (event.target.closest("label, button, a, input")) return;
      el.input.click();
    });
    const labelAccessible = el.drop.querySelector(`label[for="${el.input.id}"]`);
    if (labelAccessible) {
      if (!labelAccessible.hasAttribute("tabindex")) {
        labelAccessible.setAttribute("tabindex", "0");
      }
      labelAccessible.addEventListener("keydown", (e) => {
        if (e.key === "Enter" || e.key === " ") {
          e.preventDefault();
          el.input.click();
        }
      });
    }
    if (el.input) {
      el.input.addEventListener("invalid", () => {
        setEstadoDocumento(
          kind,
          kind === "atp" ? "Seleccioná el PDF requerido." : "Seleccioná el comprobante requerido.",
          true
        );
      });
    }
  }

  ["banco", "atp"].forEach((kind) => {
    const existente = existenteDesdeHtml(kind);
    if (existente) {
      if (kind === "banco") estado.banco = existente;
      else estado.atp = existente;
    }
    conectarDropzone(kind);
    renderDocumento(kind);
  });

  document.querySelectorAll("[data-open-doc]").forEach((boton) => {
    boton.addEventListener("click", async (event) => {
      const url = boton.dataset.openDoc;
      if (!url) return;
      event.preventDefault();
      try {
        const respuesta = await fetch(url, { credentials: "same-origin" });
        if (!respuesta.ok) throw new Error("No disponible");
        const blob = await respuesta.blob();
        const objectUrl = URL.createObjectURL(blob);
        window.open(objectUrl, "_blank", "noopener");
        setTimeout(() => URL.revokeObjectURL(objectUrl), 60000);
      } catch (error) {
        window.location.href = url;
      }
    });
  });

  if (brutoInput) {
    brutoInput.addEventListener("input", () => {
      if (modo === "alta") {
        const inlineError = $("rp-bruto-inline-error");
        if (inlineError && !inlineError.hidden) {
          inlineError.hidden = true;
          inlineError.textContent = "";
          brutoInput.removeAttribute("aria-invalid");
        }
      }
      if (!estado.baseEditada) {
        const base = $("rp-base");
        if (base) base.value = brutoInput.value;
      }
      invalidarSugerencia();
      actualizarResumen();
    });
    brutoInput.addEventListener("blur", () => {
      const raw = brutoInput.value.trim();
      const inlineError = $("rp-bruto-inline-error");
      if (raw) {
        const centavos = parseMoney(raw);
        if (centavos !== null && centavos > 0) {
          if (inlineError) {
            inlineError.hidden = true;
            inlineError.textContent = "";
          }
          brutoInput.removeAttribute("aria-invalid");
          brutoInput.value = formatMoneyEsAR(centavos);
        } else if (modo === "alta") {
          if (inlineError) {
            inlineError.hidden = false;
            inlineError.textContent = "Formato no válido. Ingresá un importe en pesos (ej.: 150.000,00).";
          }
          brutoInput.setAttribute("aria-invalid", "true");
          brutoInput.setAttribute("aria-describedby", "rp-bruto-inline-error");
        }
      } else {
        if (inlineError) {
          inlineError.hidden = true;
          inlineError.textContent = "";
        }
        brutoInput.removeAttribute("aria-invalid");
      }
      actualizarResumen();
    });
  }

  if (retencionInput) {
    retencionInput.addEventListener("input", () => {
      if (modo === "alta") {
        const inlineError = $("rp-retencion-inline-error");
        if (inlineError && inlineError.dataset.errorTipo === "formato") {
          inlineError.hidden = true;
          inlineError.textContent = "";
          delete inlineError.dataset.errorTipo;
          retencionInput.removeAttribute("aria-invalid");
        }
      }
      invalidarSugerencia();
      actualizarResumen();
    });
    retencionInput.addEventListener("blur", () => {
      const raw = retencionInput.value.trim();
      const inlineError = $("rp-retencion-inline-error");
      if (raw) {
        const centavos = parseMoney(raw);
        if (centavos !== null && centavos >= 0) {
          if (inlineError && inlineError.dataset.errorTipo === "formato") {
            inlineError.hidden = true;
            inlineError.textContent = "";
            delete inlineError.dataset.errorTipo;
            retencionInput.removeAttribute("aria-invalid");
          }
          retencionInput.value = formatMoneyEsAR(centavos);
        } else if (modo === "alta") {
          if (inlineError) {
            inlineError.hidden = false;
            inlineError.textContent = "Formato no válido. Ingresá un importe en pesos (ej.: 3.500,00 o 0).";
            inlineError.dataset.errorTipo = "formato";
          }
          retencionInput.setAttribute("aria-invalid", "true");
          retencionInput.setAttribute("aria-describedby", "rp-retencion-inline-error");
        }
      } else {
        if (inlineError && inlineError.dataset.errorTipo === "formato") {
          inlineError.hidden = true;
          inlineError.textContent = "";
          delete inlineError.dataset.errorTipo;
          retencionInput.removeAttribute("aria-invalid");
        }
      }
      actualizarResumen();
    });
  }

  if (fechaInput) {
    const alCambiarFecha = () => {
      actualizarResumen();
      sincronizarAvisoAlCorregir("fecha_pago");
    };
    fechaInput.addEventListener("input", alCambiarFecha);
    fechaInput.addEventListener("change", alCambiarFecha);
  }

  const respaldoSelect = $("id_referencia_documental");
  if (respaldoSelect) {
    respaldoSelect.addEventListener("change", actualizarResumen);
  }

  function getFechaLocalISO() {
    const d = new Date();
    const year = d.getFullYear();
    const month = String(d.getMonth() + 1).padStart(2, "0");
    const day = String(d.getDate()).padStart(2, "0");
    return `${year}-${month}-${day}`;
  }

  const btnFechaHoy = $("btn-fecha-hoy");
  if (btnFechaHoy && fechaInput && modo === "alta") {
    btnFechaHoy.addEventListener("click", () => {
      fechaInput.value = getFechaLocalISO();
      fechaInput.dispatchEvent(new Event("input", { bubbles: true }));
      actualizarResumen();
    });
  }

  const baseInput = $("rp-base");
  if (baseInput) {
    baseInput.addEventListener("input", () => {
      estado.baseEditada = true;
      invalidarSugerencia();
    });
    baseInput.addEventListener("blur", () => {
      const centavos = parseMoney(baseInput.value);
      if (centavos !== null && centavos > 0) {
        baseInput.value = formatMoneyEsAR(centavos);
      }
    });
  }

  const rateInput = $("rp-rate");
  if (rateInput) rateInput.addEventListener("input", invalidarSugerencia);

  const calc = $("rp-calc");
  if (calc) calc.addEventListener("click", calcularPorcentaje);

  const usar = $("rp-use");
  if (usar) {
    usar.addEventListener("click", () => {
      if (estado.sugerencia === null || !retencionInput) return;
      retencionInput.value = formatMoneyEsAR(estado.sugerencia);
      invalidarSugerencia();
      actualizarResumen();
    });
  }

  document.querySelectorAll('input[name="atp_decision"]').forEach((radio) => {
    radio.addEventListener("change", () => {
      if (radio.checked && radio.value === "despues") {
        quitarArchivo("atp");
        setEstadoDocumento("atp", "", false);
      }
      actualizarResumen();
      sincronizarAvisoAlCorregir("atp");
    });
  });

  // Copiado de CBU / alias con feedback accesible
  const copyBtn = $("btn-copy-cbu");
  if (copyBtn) {
    copyBtn.addEventListener("click", async () => {
      const textToCopy = copyBtn.dataset.copy || $("rp-cbu-val")?.textContent?.trim() || "";
      if (!textToCopy) return;
      try {
        if (navigator.clipboard && navigator.clipboard.writeText) {
          await navigator.clipboard.writeText(textToCopy);
        } else {
          const ta = document.createElement("textarea");
          ta.value = textToCopy;
          ta.style.position = "fixed";
          ta.style.opacity = "0";
          document.body.appendChild(ta);
          ta.select();
          document.execCommand("copy");
          document.body.removeChild(ta);
        }
        copyBtn.classList.add("copied");
        const textNode = copyBtn.querySelector(".btn-copy-text");
        if (textNode) textNode.textContent = "Copiado";
        setTimeout(() => {
          copyBtn.classList.remove("copied");
          if (textNode) textNode.textContent = "Copiar";
        }, 2000);
      } catch (err) {
        // Ignorar fallos de permisos de portapapeles
      }
    });
  }

  function validarAlta() {
    const problemas = [];
    const marcar = (id, mensaje) => problemas.push({ id, mensaje });
    if (!fechaInput?.value) marcar("id_fecha_pago", "Indicá la fecha del pago.");
    const bruto = parseMoney(brutoInput?.value);
    const retencion = parseMoney(retencionInput?.value);
    if (bruto === null || bruto <= 0) {
      marcar("id_monto_bruto", "Ingresá un bruto positivo, con hasta dos decimales.");
    }
    if (retencion === null || retencion < 0 || (bruto !== null && retencion >= bruto)) {
      marcar("id_monto_retencion_atp", "La retención debe ser menor que el monto bruto.");
    }
    if (!estado.banco) marcar("id_comprobante_bancario", "Seleccioná el comprobante bancario (PDF o imagen).");
    if (retencion !== null && retencion > 0) {
      const decision = document.querySelector('input[name="atp_decision"]:checked')?.value;
      if (!decision) {
        marcar("id_atp_decision_0", "Elegí si adjuntás la constancia ATP ahora o después.");
      } else if (decision === "ahora" && !estado.atp) {
        marcar("id_constancia_atp", "Seleccioná el PDF de la constancia ATP o elegí incorporarla después.");
      }
    }
    return problemas;
  }

  function validarBasica() {
    const problemas = [];
    const marcar = (id, mensaje) => problemas.push({ id, mensaje });
    if (!fechaInput?.value) marcar("id_fecha_pago", "Indicá la fecha del pago.");
    const bruto = parseMoney(brutoInput?.value);
    const retencion = parseMoney(retencionInput?.value);
    if (bruto === null || bruto <= 0) marcar("id_monto_bruto", "Ingresá un bruto positivo.");
    if (retencion === null || retencion < 0 || (bruto !== null && retencion >= bruto)) {
      marcar("id_monto_retencion_atp", "La retención debe ser menor que el bruto.");
    }
    const motivo = $("id_motivo");
    if (motivo && !motivo.value.trim()) marcar("id_motivo", "El motivo es obligatorio.");
    return problemas;
  }

  let submitInvalidoOcurrido = Boolean(
    modo === "alta" && form?.dataset.hasServerErrors === "true"
  );

  function actualizarAvisoSubmit(problemas) {
    if (modo !== "alta") return;
    const aviso = $("rp-submit-error-notice");
    if (!aviso) return;
    if (!problemas || !problemas.length) {
      aviso.hidden = true;
      aviso.textContent = "";
      return;
    }
    aviso.hidden = false;
    aviso.textContent = problemas.length === 1
      ? `Falta revisar: ${problemas[0].mensaje}`
      : `Revisá los ${problemas.length} campos observados antes de registrar el pago.`;
  }

  function obtenerErroresActuales() {
    if (modo !== "alta") return [];
    const problemasCliente = validarAlta();

    const problemasServidor = [];
    const serverErrorEls = form.querySelectorAll(
      ".rp-error:not(#rp-errores):not(#rp-submit-error-notice):not(#rp-aviso-respaldo-faltante):not([hidden])"
    );
    serverErrorEls.forEach((errEl) => {
      const container = errEl.closest("div, section");
      const input = container?.querySelector("input, select, textarea");
      const txt = errEl.textContent.trim();
      if (input && txt) {
        if (!problemasCliente.some((p) => p.id === input.id)) {
          problemasServidor.push({ id: input.id, mensaje: txt });
        }
      }
    });

    return [...problemasCliente, ...problemasServidor];
  }

  function sincronizarAvisoAlCorregir(campo) {
    if (modo !== "alta" || !submitInvalidoOcurrido) return;

    if (campo === "fecha_pago" && fechaInput?.value) {
      fechaInput.removeAttribute("aria-invalid");
      const errEl = fechaInput.closest("div")?.querySelector(".rp-error:not(#rp-errores)");
      if (errEl) errEl.hidden = true;
    }

    if (campo === "banco" && estado.banco) {
      setEstadoDocumento("banco", "", false);
      const input = $("id_comprobante_bancario");
      if (input) input.removeAttribute("aria-invalid");
      const errEl = $("rp-banco-drop")?.parentElement?.querySelector(".rp-error:not(#rp-errores)");
      if (errEl) errEl.hidden = true;
    }

    if (campo === "atp") {
      const decision = document.querySelector('input[name="atp_decision"]:checked')?.value;
      const retencion = parseMoney(retencionInput?.value);
      if (estado.atp || decision === "despues" || retencion === 0) {
        setEstadoDocumento("atp", "", false);
        const input = $("id_constancia_atp");
        if (input) input.removeAttribute("aria-invalid");
        const errEl = $("rp-atp-drop")?.parentElement?.querySelector(".rp-error:not(#rp-errores)");
        if (errEl) errEl.hidden = true;
      }
    }

    if (errores && !errores.hidden) {
      const items = errores.querySelectorAll("li");
      items.forEach((item) => {
        const link = item.querySelector("a");
        const href = link?.getAttribute("href");
        if (
          (campo === "fecha_pago" && href === "#id_fecha_pago" && fechaInput?.value) ||
          (campo === "banco" && href === "#id_comprobante_bancario" && estado.banco) ||
          (campo === "atp" && href === "#id_constancia_atp" && (estado.atp || document.querySelector('input[name="atp_decision"]:checked')?.value === "despues"))
        ) {
          item.remove();
        }
      });
      if (errores.querySelectorAll("li").length === 0) {
        errores.hidden = true;
        errores.replaceChildren();
      }
    }

    const problemas = obtenerErroresActuales();
    actualizarAvisoSubmit(problemas);
  }

  function enfocarYDesplazarPrimerError(primerElemento) {
    if (!primerElemento) return;
    const parentDetails = primerElemento.closest("details");
    if (parentDetails && !parentDetails.open) {
      parentDetails.open = true;
    }
    const prefersReducedMotion = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    let elementoScroll = primerElemento;
    let elementoFoco = primerElemento;

    if (
      primerElemento.classList?.contains("rp-file-input") ||
      primerElemento.type === "file" ||
      primerElemento.id === "id_comprobante_bancario" ||
      primerElemento.id === "id_constancia_atp"
    ) {
      const dropzone =
        primerElemento.closest(".rp-dropzone") ||
        (primerElemento.id === "id_comprobante_bancario"
          ? $("rp-banco-drop")
          : $("rp-atp-drop"));
      if (dropzone) {
        elementoScroll = dropzone;
        const labelBtn = dropzone.querySelector(
          `label[for="${primerElemento.id}"], label.rp-button, button`
        );
        if (labelBtn) {
          elementoFoco = labelBtn;
          if (!labelBtn.hasAttribute("tabindex")) {
            labelBtn.setAttribute("tabindex", "0");
          }
        }
      }
    }

    elementoScroll.scrollIntoView({
      behavior: prefersReducedMotion ? "auto" : "smooth",
      block: "center",
    });
    try {
      elementoFoco.focus({ preventScroll: true });
    } catch (e) {
      if (typeof elementoFoco.focus === "function") elementoFoco.focus();
    }
  }

  function mostrarProblemas(problemas) {
    if (!errores) return;
    errores.replaceChildren();
    if (!problemas.length) {
      errores.hidden = true;
      actualizarAvisoSubmit([]);
      return;
    }
    errores.hidden = false;
    const titulo = document.createElement("p");
    titulo.textContent = "Revisá estos datos antes de continuar:";
    const lista = document.createElement("ul");
    problemas.forEach(({ id, mensaje }) => {
      const item = document.createElement("li");
      const enlace = document.createElement("a");
      enlace.href = `#${id}`;
      enlace.textContent = mensaje;
      item.append(enlace);
      lista.append(item);
      const campo = document.getElementById(id);
      if (campo) campo.setAttribute("aria-invalid", "true");
    });
    errores.append(titulo, lista);
    actualizarAvisoSubmit(problemas);
    const primero = document.getElementById(problemas[0].id) || errores;
    enfocarYDesplazarPrimerError(primero);
  }

  if (form && modo === "alta") {
    form.addEventListener("invalid", (e) => {
      const target = e.target;
      if (!target) return;
      actualizarAvisoSubmit([{ id: target.id, mensaje: target.validationMessage || "Revisá este campo." }]);
      enfocarYDesplazarPrimerError(target);
    }, true);
  }

  if (form && (modo === "alta" || modo === "rectificacion" || modo === "atp")) {
    form.addEventListener("submit", (event) => {
      form.querySelectorAll("[aria-invalid]").forEach((nodo) => nodo.removeAttribute("aria-invalid"));
      const problemas = modo === "atp" ? validarAtp() : modo === "alta" ? validarAlta() : validarBasica();
      if (problemas.length) {
        event.preventDefault();
        submitInvalidoOcurrido = true;
        if (modo === "alta") {
          if (!estado.banco) {
            setEstadoDocumento(
              "banco",
              "Seleccioná el comprobante bancario (PDF o imagen).",
              true
            );
          }
          const retencion = parseMoney(retencionInput?.value);
          const decision = document.querySelector('input[name="atp_decision"]:checked')?.value;
          if (retencion !== null && retencion > 0 && decision === "ahora" && !estado.atp) {
            setEstadoDocumento(
              "atp",
              "Seleccioná el PDF de la constancia ATP o elegí incorporarla después.",
              true
            );
          }
        } else if (modo === "atp") {
          if (!estado.atp) {
            setEstadoDocumento("atp", "Seleccioná el PDF de la constancia ATP.", true);
          }
        }
        mostrarProblemas(problemas);
        return;
      }
      submitInvalidoOcurrido = false;
      mostrarProblemas([]);

      const decision = document.querySelector('input[name="atp_decision"]:checked')?.value;
      if (decision === "despues") {
        const atpRef = $("id_referencia_atp");
        if (atpRef) {
          atpRef.value = "";
          atpRef.disabled = true;
        }
        const atpFile = $("id_constancia_atp");
        if (atpFile) atpFile.disabled = true;
      }

      if (brutoInput) brutoInput.value = canonico(brutoInput.value);
      if (retencionInput) retencionInput.value = canonico(retencionInput.value);
      const boton = form.querySelector('button[type="submit"]');
      if (boton) setTimeout(() => { boton.disabled = true; }, 0);
    });
  }

  function validarAtp() {
    const problemas = [];
    if (!estado.atp) {
      problemas.push({ id: "id_constancia_atp", mensaje: "Seleccioná el PDF de la constancia ATP." });
    }
    const motivo = $("id_motivo");
    if (motivo && !motivo.value.trim()) {
      problemas.push({ id: "id_motivo", mensaje: "El motivo del aporte es obligatorio." });
    }
    return problemas;
  }

  // Foco/scroll ante errores devueltos por el servidor (POST) en alta; no enfocar en GET normal
  if (modo === "alta" && form?.dataset.hasServerErrors === "true") {
    const errorContainers = form.querySelectorAll(".rp-error:not(#rp-errores):not(#rp-submit-error-notice):not([hidden])");
    let primerCampo = null;
    const fallosServidor = [];
    errorContainers.forEach((errEl) => {
      const container = errEl.closest("div, section");
      const input = container?.querySelector("input, select, textarea");
      const txt = errEl.textContent.trim();
      if (input && !primerCampo) primerCampo = input;
      if (input && txt) fallosServidor.push({ id: input.id, mensaje: txt });
    });
    if (!primerCampo) primerCampo = $("rp-errores");
    if (primerCampo) {
      enfocarYDesplazarPrimerError(primerCampo);
    }
    if (fallosServidor.length) {
      actualizarAvisoSubmit(fallosServidor);
    }
  }

  actualizarResumen();
})();