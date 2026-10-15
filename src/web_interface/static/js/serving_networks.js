/* Workspace Config → Serving Networks: choose the networks that serve each Operator by clicking them. */
(() => {
  'use strict';

  const form = document.querySelector('[data-serving-networks-form]');
  if (!form) return;

  let data = {};
  try {
    data = JSON.parse(form.querySelector('[data-serving-networks-data]').textContent || '{}') || {};
  } catch (error) {
    data = {};
  }
  const body = form.querySelector('[data-serving-networks-rows]');
  const csv = form.querySelector('[data-serving-networks-csv]');
  const status = form.querySelector('[data-serving-networks-status]');
  const networks = data.networks || [];
  const labels = new Map(networks.map((item) => [item.family, item.label]));
  const label = (family) => labels.get(family) || family;
  // The networks chosen for each Operator, in order of preference, and those last saved.
  const rows = (data.rows || []).map((row) => ({...row, chosen: [...row.networks], saved: [...row.networks]}));
  const same = (left, right) => left.length === right.length && left.every((value, index) => value === right[index]);
  const escape = (value) => String(value).replace(/[&<>"']/g, (character) => `&#${character.charCodeAt(0)};`);

  const chosenChip = (index, family, position, only) => `<button type="button" class="serving-network-chip is-chosen" data-row="${index}" data-remove="${escape(family)}"${only ? ' disabled title="An Operator needs at least one serving network: add another one first."' : ` title="Remove ${escape(label(family))}"`}><span class="serving-network-rank">${position + 1}</span>${escape(label(family))}${only ? '' : '<span class="serving-network-remove" aria-hidden="true">×</span>'}</button>`;
  const optionChip = (index, family) => `<button type="button" class="serving-network-chip" data-row="${index}" data-add="${escape(family)}" title="Add ${escape(label(family))} as the next serving network">+ ${escape(label(family))}</button>`;

  const render = () => {
    body.innerHTML = rows.map((row, index) => {
      const chosen = row.chosen.map((family, position) => chosenChip(index, family, position, row.chosen.length === 1))
        .join('<span class="serving-network-arrow" aria-hidden="true">→</span>');
      const options = networks.filter((item) => !row.chosen.includes(item.family)).map((item) => optionChip(index, item.family)).join('');
      const isDefault = same(row.chosen, row.defaults);
      const reset = isDefault ? '' : `<button type="button" class="serving-network-reset" data-row="${index}" data-reset title="Served by ${escape(row.defaults.map(label).join(' → '))}">Use default</button>`;
      return `<tr class="${same(row.chosen, row.saved) ? '' : 'is-changed'}">
        <td data-label="Operator">${escape(row.operator)}</td>
        <td data-label="Served by the cells of"><div class="serving-network-order">${chosen}</div>${options ? `<div class="serving-network-options">${options}</div>` : ''}</td>
        <td data-label="Source"><span class="serving-network-source">${isDefault ? 'Default' : 'Configured'}</span>${reset}</td></tr>`;
    }).join('');
    // Only the Operators that differ from their defaults are saved; the others keep following the defaults.
    const lines = rows.filter((row) => !same(row.chosen, row.defaults)).map((row) => `${row.operator},${row.chosen.map(label).join('; ')}`);
    csv.value = lines.length ? `Operator,Serving Networks\n${lines.join('\n')}\n` : '';
    const changed = rows.filter((row) => !same(row.chosen, row.saved)).length;
    status.textContent = changed ? `Unsaved changes in ${changed} Operator${changed === 1 ? '' : 's'}: save them to apply them.` : '';
  };

  body.addEventListener('click', (event) => {
    const button = event.target.closest('button[data-row]');
    if (!button || button.disabled) return;
    const row = rows[Number(button.dataset.row)];
    if (!row) return;
    if (button.dataset.remove) row.chosen = row.chosen.filter((family) => family !== button.dataset.remove);
    else if (button.dataset.add) row.chosen = [...row.chosen, button.dataset.add];
    else if (button.hasAttribute('data-reset')) row.chosen = [...row.defaults];
    render();
  });

  render();
})();
