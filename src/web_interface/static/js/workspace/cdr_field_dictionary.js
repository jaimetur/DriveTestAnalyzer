/* Workspace Config → CDR Field Dictionary: find fields, mark the changed ones and return a field to its default. */
(() => {
  'use strict';

  const form = document.querySelector('[data-cdr-field-dictionary-form]');
  if (!form) return;

  const filter = form.querySelector('[data-cdr-field-dictionary-filter]');
  const changedOnly = form.querySelector('[data-cdr-field-dictionary-changed]');
  const status = form.querySelector('[data-cdr-field-dictionary-status]');
  const rows = [...form.querySelectorAll('[data-cdr-field-row]')];
  // The columns of a field as they are compared: trimmed, without empty ones, regardless of case and spaces.
  const columns = (value) => String(value || '').split(';').map((item) => item.trim().replace(/\s+/g, ' ').toLowerCase()).filter(Boolean).join(';');
  const input = (row) => row.querySelector('input[name^="field:"]');
  const isChanged = (row) => {
    const field = input(row);
    // An empty field returns to its default.
    return Boolean(columns(field.value)) && columns(field.value) !== columns(field.dataset.default);
  };

  const refresh = () => {
    const words = String(filter?.value || '').trim().toLowerCase().split(/\s+/).filter(Boolean);
    let changed = 0;
    rows.forEach((row) => {
      const modified = isChanged(row);
      changed += Number(modified);
      row.classList.toggle('is-changed', modified);
      row.querySelector('[data-cdr-field-default]').hidden = !modified;
      const text = `${row.dataset.search || ''} ${input(row).value.toLowerCase()}`;
      row.hidden = (changedOnly?.checked && !modified) || !words.every((word) => text.includes(word));
    });
    form.querySelectorAll('[data-cdr-field-dictionary-section]').forEach((section) => {
      section.hidden = ![...section.querySelectorAll('[data-cdr-field-row]')].some((row) => !row.hidden);
    });
    if (status) status.textContent = changed ? `${changed} field${changed === 1 ? '' : 's'} not default` : 'Every field reads its default columns';
  };

  rows.forEach((row) => {
    input(row).addEventListener('input', refresh);
    row.querySelector('[data-cdr-field-default]').addEventListener('click', () => {
      input(row).value = input(row).dataset.default || '';
      refresh();
      input(row).focus();
    });
  });
  filter?.addEventListener('input', refresh);
  changedOnly?.addEventListener('change', refresh);
  refresh();
})();
