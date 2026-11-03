/* Workspace Config → Map Areas: the administrative areas of each country of the tests. */
(() => {
  'use strict';

  const root = document.querySelector('[data-map-areas]');
  if (!root) return;

  const $ = (selector) => root.querySelector(selector);
  const node = (tag, text, className) => {
    const element = document.createElement(tag);
    if (text !== undefined && text !== null) element.textContent = text;
    if (className) element.className = className;
    return element;
  };
  const number = (value) => Number(value || 0).toLocaleString('en-US');
  const message = (text, tone = '') => {
    const target = $('[data-map-area-message]');
    target.textContent = text;
    target.classList.toggle('is-error', tone === 'error');
    target.classList.toggle('is-success', tone === 'success');
  };
  async function api(path, options = {}) {
    const response = await fetch(path, {credentials: 'same-origin', ...options});
    const body = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(body.detail || `Request failed (${response.status}).`);
    return body;
  }
  const table = (headers, rows) => {
    const element = node('table', undefined, 'operator-mappings-table map-areas-table');
    const head = element.createTHead().insertRow();
    headers.forEach((header) => head.append(node('th', header)));
    const body = element.createTBody();
    rows.forEach((cells) => {
      const row = body.insertRow();
      cells.forEach((content) => {
        const cell = row.insertCell();
        if (content instanceof Node) cell.append(content); else cell.textContent = content ?? '';
      });
    });
    return element;
  };
  const layerText = (layer) => `${layer.level_label} · ${number(layer.unit_count)} areas · ${layer.origin}`;

  // Saved layers: one per country.
  async function renderLayers() {
    const {layers} = await api('/api/workspace-config/map-areas');
    const target = $('[data-map-area-layers]');
    if (!layers.length) {
      target.replaceChildren(node('p', 'No Map Areas saved yet: each country uses the areas included with the application, or else the whole country as one area.', 'form-note'));
      return layers;
    }
    target.replaceChildren(table(['Country', 'Areas', 'Source', 'Licence', 'Updated', 'Actions'], layers.map((layer) => {
      const remove = node('button', 'Delete', 'danger-button');
      remove.type = 'button';
      remove.addEventListener('click', async () => {
        const confirmed = typeof window.showConfirmDialog === 'function'
          ? await window.showConfirmDialog(`Delete the Map Areas of ${layer.country_name}? Scoring jobs calculated again will show its tests as bubbles.`,
            {title: 'Delete Map Areas?', confirmLabel: 'Delete'})
          : window.confirm(`Delete the Map Areas of ${layer.country_name}?`);
        if (!confirmed) return;
        try {
          await api(`/api/workspace-config/map-areas/${layer.id}`, {method: 'DELETE'});
          message(`Map Areas of ${layer.country_name} deleted.`, 'success');
          await refresh();
        } catch (error) { message(error.message, 'error'); }
      });
      return [`${layer.country_name} (${layer.country_code})`, `${layer.level_label} · ${number(layer.unit_count)}`,
        layer.source, layer.license, String(layer.updated_at || '').slice(0, 16).replace('T', ' '), remove];
    })));
    return layers;
  }

  // Saved postal code layers: one per country.
  async function renderPostalLayers() {
    const {layers} = await api('/api/workspace-config/map-areas/postal');
    const target = $('[data-postal-area-layers]');
    if (!layers.length) {
      target.replaceChildren(node('p', 'No Postal Codes saved in this workspace yet: a calculation that asks for them downloads them, or choose or download them in Countries of the tests. Until then, a country with a copy included with the application uses that copy.', 'form-note'));
      return;
    }
    target.replaceChildren(table(['Country', 'Areas', 'Source', 'Licence', 'Updated', 'Actions'], layers.map((layer) => {
      const remove = node('button', 'Delete', 'danger-button');
      remove.type = 'button';
      remove.addEventListener('click', async () => {
        const confirmed = typeof window.showConfirmDialog === 'function'
          ? await window.showConfirmDialog(`Delete the Postal Codes of ${layer.country_name}? A calculation that asks for them downloads them again.`,
            {title: 'Delete Postal Codes?', confirmLabel: 'Delete'})
          : window.confirm(`Delete the Postal Codes of ${layer.country_name}?`);
        if (!confirmed) return;
        try {
          await api(`/api/workspace-config/map-areas/postal/${layer.id}`, {method: 'DELETE'});
          message(`Postal Codes of ${layer.country_name} deleted.`, 'success');
          await refresh();
        } catch (error) { message(error.message, 'error'); }
      });
      return [`${layer.country_name} (${layer.country_code})`, `${layer.level} · ${number(layer.unit_count)}`,
        layer.origin, layer.license, String(layer.updated_at || '').slice(0, 16).replace('T', ' '), remove];
    })));
  }

  // The postal codes of a country, downloaded from GeoNames into the workspace: its full postcodes (about a minute) or one
  // point per place.
  async function downloadPostal(country, full) {
    message(`Downloading the postal codes of ${country.name}${full ? ' (about a minute)' : ''}…`);
    const {layer} = await api('/api/workspace-config/map-areas/postal/download', {
      method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({country_code: country.code, full}),
    });
    message(`${layer.country_name}: ${number(layer.unit_count)} postal code areas saved. Calculate the scoring again to use them.`, 'success');
  }

  // A file of the workspace is chosen in the import form, ready for this country.
  function openPostalImport(country) {
    const form = $('[data-map-area-import]');
    form.elements.layer.value = 'postal-codes';
    form.elements.country_code.value = country.code;
    form.scrollIntoView({block: 'center'});
    form.elements.file.focus();
    message(`Choose the file with the postal code areas of ${country.name} and press Import areas.`);
  }

  // The map of the Postal Codes of a country, saved in the workspace: the one worked out from its full postcodes or from
  // the points per place of GeoNames, or a file of the workspace. It applies as soon as it is chosen. Without one saved, a
  // copy included with the application stands in for the full postcodes.
  function postalChooser(country) {
    const layer = country.postal_layer;
    const fullSaved = layer?.origin === 'GeoNames full postcodes';
    const current = layer ? (fullSaved ? 'full' : layer.origin === 'GeoNames' ? 'place' : 'own') : (country.postal_full ? 'full' : 'place');
    const fullAreas = fullSaved ? layer.unit_count : country.postal_bundled?.unit_count;
    // A failed download leaves what the workspace has, which is worth saying when that is the copy of the application.
    const failed = (error) => (!layer && country.postal_bundled
      ? `${error.message} The copy included with the application stays in use.` : error.message);
    const box = node('div', undefined, 'map-area-chooser');
    const select = node('select');
    select.setAttribute('aria-label', `Map of the Postal Codes of ${country.name}`);
    select.dataset.postalMap = country.code;
    const options = [
      ...(country.postal_full ? [['full', `Full postcodes${fullAreas ? ` · ${number(fullAreas)} areas` : ''} (default)`]] : []),
      ['place', layer && current === 'place' ? `One point per place · ${number(layer.unit_count)} areas` : 'One point per place'],
      ['own', current === 'own' ? `Own file · ${layer.source} · ${number(layer.unit_count)} areas` : 'Own file'],
    ];
    for (const [value, text] of options) {
      const option = node('option', text);
      option.value = value;
      option.selected = value === current;
      select.append(option);
    }
    select.addEventListener('change', async () => {
      const chosen = select.value;
      if (chosen === 'own') {
        select.value = current;
        openPostalImport(country);
        return;
      }
      if (current === 'own') {
        const text = `Use another map for the Postal Codes of ${country.name}? ${layer.source} is removed from the workspace.`;
        const confirmed = typeof window.showConfirmDialog === 'function'
          ? await window.showConfirmDialog(text, {title: 'Replace your map?', confirmLabel: 'Replace'}) : window.confirm(text);
        if (!confirmed) {
          select.value = current;
          return;
        }
      }
      select.disabled = true;
      try {
        await downloadPostal(country, chosen === 'full');
        await refresh();
      } catch (error) {
        message(failed(error), 'error');
        await renderCountries().catch(() => {});
      }
    });
    box.append(select);
    if (current !== 'own') {
      const download = node('button', layer ? 'Download again' : 'Download now', 'secondary-button');
      download.type = 'button';
      download.addEventListener('click', async () => {
        download.disabled = true;
        try {
          await downloadPostal(country, current === 'full');
          await refresh();
        } catch (error) {
          message(failed(error), 'error');
          download.disabled = false;
        }
      });
      box.append(download);
    }
    return box;
  }

  // The levels of a country, chosen and downloaded from geoBoundaries.
  function levelChooser(country) {
    const box = node('div', undefined, 'map-area-chooser');
    const load = node('button', country.layer ? 'Change areas…' : 'Choose areas…', 'secondary-button');
    load.type = 'button';
    box.append(load);
    load.addEventListener('click', async () => {
      load.disabled = true;
      load.textContent = 'Loading levels…';
      try {
        const {levels} = await api(`/api/workspace-config/map-areas/levels/${encodeURIComponent(country.code)}`);
        const select = node('select');
        select.setAttribute('aria-label', `Level of the areas of ${country.name}`);
        for (const level of levels) {
          const option = node('option', `${level.label} (${level.level}) · ${number(level.count)} areas · ${level.license}`
            + `${level.commercial ? '' : ' · non-commercial'}${level.too_large ? ' · too many areas' : ''}`);
          option.value = level.level;
          option.disabled = level.too_large || !level.url;
          if (level.suggested) { option.selected = true; option.textContent += ' · suggested'; }
          select.append(option);
        }
        const download = node('button', 'Download');
        download.type = 'button';
        download.addEventListener('click', async () => {
          const chosen = levels.find((level) => level.level === select.value);
          if (chosen && !chosen.commercial && !window.confirm(`The licence of these areas (${chosen.license}) does not allow commercial use. Download them anyway?`)) return;
          download.disabled = true;
          download.textContent = 'Downloading…';
          message(`Downloading the ${chosen?.label || 'areas'} of ${country.name}; large countries can take a minute…`);
          try {
            const {layer} = await api('/api/workspace-config/map-areas/download', {
              method: 'POST', headers: {'Content-Type': 'application/json'},
              body: JSON.stringify({country_code: country.code, level: select.value}),
            });
            message(`${layer.country_name}: ${number(layer.unit_count)} ${layer.level_label} areas saved. Calculate the scoring again to use them.`, 'success');
            await refresh();
          } catch (error) {
            message(error.message, 'error');
            download.disabled = false;
            download.textContent = 'Download';
          }
        });
        box.replaceChildren(select, download);
      } catch (error) {
        message(error.message, 'error');
        load.disabled = false;
        load.textContent = 'Choose areas…';
      }
    });
    return box;
  }

  async function renderCountries() {
    const target = $('[data-map-area-countries]');
    target.replaceChildren(node('p', 'Finding the countries of the tests…', 'form-note'));
    const {countries} = await api('/api/workspace-config/map-areas/countries');
    if (!countries.length) {
      target.replaceChildren(node('p', 'No ready CDR has test coordinates yet.', 'form-note'));
      return;
    }
    target.replaceChildren(table(['Country', 'Tests', 'Map Areas', 'Postal Codes', 'Actions'], countries.map((country) => [
      `${country.name} (${country.code})`,
      `${(country.share * 100).toFixed(country.share < .01 ? 2 : 1)}%`,
      country.layer ? layerText(country.layer)
        : country.bundled ? `${country.bundled.level_label} · ${number(country.bundled.unit_count)} areas · included with the application`
          : node('strong', 'None: the whole country is one area', 'map-area-missing'),
      postalChooser(country),
      // Any country can replace the areas included with the application with its own.
      levelChooser(country),
    ])));
  }

  async function refresh() {
    await renderLayers();
    await renderPostalLayers();
    await renderCountries();
  }

  $('[data-map-area-detect]').addEventListener('click', () => { renderCountries().catch((error) => message(error.message, 'error')); });
  $('[data-map-area-import]').addEventListener('submit', async (event) => {
    event.preventDefault();
    const form = event.currentTarget;
    const button = form.querySelector('button[type="submit"]');
    button.disabled = true;
    message('Importing the areas…');
    try {
      const {layer} = await api('/api/workspace-config/map-areas/import', {method: 'POST', body: new FormData(form)});
      message(`${layer.country_name}: ${number(layer.unit_count)} ${layer.level_label} areas imported. Calculate the scoring again to use them.`, 'success');
      form.reset();
      await refresh();
    } catch (error) {
      message(error.message, 'error');
    } finally {
      button.disabled = false;
    }
  });
  refresh().catch((error) => message(error.message, 'error'));
})();
