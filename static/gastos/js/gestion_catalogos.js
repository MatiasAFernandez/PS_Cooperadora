/**
 * Gestión de Catálogos y Parámetros Operativos — PS_Cooperadora
 * Comportamiento nativo progresivo para la administración de Centros de Costo.
 * Funcionalidades:
 *  - Activación de herramientas de búsqueda y filtrado de centros.
 *  - Filtrado en tiempo real por texto (código / nombre descriptivo) insensible a acentos.
 *  - Filtrado por estado (Todos / Activos / Inactivos).
 *  - Estado vacío accesible (role="status") cuando no hay coincidencias.
 *  - Acordeón y control de detalles de edición y confirmación de baja.
 *  - Cierre intuitivo de detalles con tecla Escape o clic exterior.
 *  - Foco accesible en campos con error o al desplegar edición.
 *  - Conserva 100% de la funcionalidad de formularios sin JavaScript.
 */

(function () {
  'use strict';

  function initCatalogos() {
    const toolsContainer = document.querySelector('[data-catalog-tools]');
    const searchInput = document.getElementById('catalog-search');
    const statusSelect = document.getElementById('catalog-status');
    const emptyNotice = document.querySelector('[data-catalog-empty]');
    const catalogTable = document.querySelector('.catalog-table');
    const rows = Array.from(document.querySelectorAll('[data-catalog-row]'));

    // 1. Mostrar herramientas de búsqueda y filtrado al disponer de JavaScript
    if (toolsContainer) {
      toolsContainer.hidden = false;
      toolsContainer.removeAttribute('hidden');
    }

    // Normalizador de cadenas de texto (minúsculas y remoción de tildes/diacríticos)
    function normalize(text) {
      return (text || '')
        .toLowerCase()
        .normalize('NFD')
        .replace(/[\u0300-\u036f]/g, '')
        .trim();
    }

    // 2. Filtrado reactivo en cliente (búsqueda textual + estado activo/inactivo)
    function filterRows() {
      const query = searchInput ? normalize(searchInput.value) : '';
      const filterStatus = statusSelect ? statusSelect.value : '';
      let visibleCount = 0;

      rows.forEach((row) => {
        const codeEl = row.querySelector('[data-catalog-code]');
        const nameEl = row.querySelector('[data-catalog-name]');
        const codeText = codeEl ? normalize(codeEl.textContent) : '';
        const nameText = nameEl ? normalize(nameEl.textContent) : '';
        const rowStatus = row.getAttribute('data-status') || '';

        const matchesQuery = !query || codeText.includes(query) || nameText.includes(query);
        const matchesStatus = !filterStatus || rowStatus === filterStatus;

        if (matchesQuery && matchesStatus) {
          row.hidden = false;
          row.removeAttribute('hidden');
          visibleCount += 1;
        } else {
          row.hidden = true;
          row.setAttribute('hidden', '');
          // Cerrar detalles abiertos dentro de filas que pasan a estar ocultas
          const openDetails = row.querySelector('details[open]');
          if (openDetails) {
            openDetails.removeAttribute('open');
          }
        }
      });

      if (emptyNotice) {
        if (visibleCount === 0) {
          emptyNotice.hidden = false;
          emptyNotice.removeAttribute('hidden');
          if (catalogTable) {
            catalogTable.style.display = 'none';
          }
        } else {
          emptyNotice.hidden = true;
          emptyNotice.setAttribute('hidden', '');
          if (catalogTable) {
            catalogTable.style.display = '';
          }
        }
      }
    }

    if (searchInput) {
      searchInput.addEventListener('input', filterRows);
      searchInput.addEventListener('search', filterRows);
    }

    if (statusSelect) {
      statusSelect.addEventListener('change', filterRows);
    }

    // 3. Manejo de detalles (Edición en línea y Confirmación de baja)
    const actionDetails = Array.from(document.querySelectorAll('.catalog-action'));

    actionDetails.forEach((details) => {
      details.addEventListener('toggle', () => {
        if (details.open) {
          // Comportamiento de acordeón: cerrar otros detalles para no sobrecargar la tabla
          actionDetails.forEach((other) => {
            if (other !== details && other.open) {
              other.removeAttribute('open');
            }
          });

          // Foco accesible al campo de texto cuando se abre edición
          const nameInput = details.querySelector('input[name="nombre"]');
          if (nameInput) {
            nameInput.focus();
            nameInput.select();
          }
        }
      });
    });

    // Cierre accesible con tecla Escape
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') {
        actionDetails.forEach((details) => {
          if (details.open) {
            details.removeAttribute('open');
            const summary = details.querySelector('summary');
            if (summary) {
              summary.focus();
            }
          }
        });
      }
    });

    // Cierre al hacer clic fuera del panel abierto
    document.addEventListener('click', (event) => {
      actionDetails.forEach((details) => {
        if (details.open && !details.contains(event.target)) {
          details.removeAttribute('open');
        }
      });
    });

    // 4. Preservación y accesibilidad de estados de error del servidor
    const firstInvalid = document.querySelector('[aria-invalid="true"]');
    if (firstInvalid) {
      firstInvalid.focus();
    }
  }

  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', initCatalogos);
  } else {
    initCatalogos();
  }
})();
