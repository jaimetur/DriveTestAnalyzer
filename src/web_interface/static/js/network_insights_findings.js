/* Network Insights Key Findings: six benchmark views of the Data tests drawn as slides, in the colours of the theme. */
(() => {
  'use strict';
  const escapeHtml = value => String(value ?? '').replace(/[&<>"']/g, character => ({'&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;'}[character]));
  const hex = (value, fallback = '#888888') => {
    const text = String(value || '').trim().replace(/^#/, '');
    return /^[0-9a-f]{6}$/i.test(text) ? `#${text.toUpperCase()}` : fallback;
  };
  const channels = value => [1, 3, 5].map(index => parseInt(hex(value).slice(index, index + 2), 16));
  const luminance = value => {
    const [red, green, blue] = channels(value).map(channel => channel / 255);
    return 0.2126 * red + 0.7152 * green + 0.0722 * blue;
  };
  const blend = (start, end, amount) => {
    const from = channels(start);
    const to = channels(end);
    return `#${from.map((channel, index) => Math.round(channel + (to[index] - channel) * Math.max(0, Math.min(1, amount)))
      .toString(16).padStart(2, '0')).join('').toUpperCase()}`;
  };

  // The colours of the views in a theme (see network_insights_findings_slides.palette): on the page each card keeps
  // the surface of the theme, dark in Midnight.
  const palette = (theme = {}) => {
    const surface = hex(theme.surface, '#FFFFFF');
    const dark = luminance(surface) < .5;
    const ink = hex(theme.ink, '#1F2A37');
    return {
      surface, ink, dark, muted: hex(theme.muted, '#8A96A0'), accent: hex(theme.title_accent, '#1450A8'),
      soft: dark ? blend(surface, ink, .08) : (luminance(hex(theme.soft_header, '#EDF2F6')) < .8
        ? blend(hex(theme.soft_header), '#FFFFFF', .85)
        // A white panel stands apart from the card in the shade of the groups of the theme.
        : luminance(hex(theme.soft_header, '#EDF2F6')) > .99 ? hex(theme.group, '#F5F5F5') : hex(theme.soft_header, '#EDF2F6')),
      line: hex(theme.line, '#E3E8EC'),
      scale: (theme.scale || ['#C9483F', '#E8A060', '#F2D06B', '#93C47D', '#3E8E4F']).map(colour => hex(colour)),
      series: (theme.series || ['#5B7A99', '#A9C4DB', '#8BA88E', '#C9B27C', '#B48C7C', '#8E87A0', '#DADDE0']).map(colour => hex(colour)),
      track: blend(hex(theme.muted, '#8A96A0'), surface, .45),
      font: theme.font || '',
      // The tables of the page: the header of the theme, alternate rows (a shade of the surface on a dark theme).
      header: hex(theme.header, '#455B65'), headerText: hex(theme.header_text, '#FFFFFF'),
      rowAlt: dark ? blend(surface, ink, .05) : hex(theme.row_alt, '#F8FAFC'),
      hover: dark ? blend(surface, ink, .1) : blend(hex(theme.row_alt, '#F8FAFC'), ink, .05),
      gain: hex(theme.gain, '#4CA65A'), loss: hex(theme.loss, '#E8414F'),
      // The title and the headline of the views in the style of the slides of the theme (see theme_titles.py).
      title: dark ? ink : hex(theme.title, '#1F2A37'),
      headline: hex(theme.titles?.subtitle_color || theme.subtitle, '#245A96'),
      titleFont: theme.titles?.font ? `"${theme.titles.font}", ${theme.font || 'inherit'}` : '',
      titleWeight: theme.titles?.bold === false ? 400 : 850,
      titleCaps: Boolean(theme.titles?.caps), headlineItalic: Boolean(theme.titles?.subtitle_italic),
    };
  };
  const ladderColours = (colours, count) => {
    const scale = [...colours.scale].reverse();
    return Array.from({length: count}, (_, index) => {
      const position = index / Math.max(1, count - 1) * (scale.length - 1);
      const low = Math.floor(position);
      return blend(scale[low], scale[Math.min(scale.length - 1, low + 1)], position - low);
    });
  };
  const rankColour = (colours, rank) => (rank === null || rank === undefined ? colours.track
    : colours.scale[Math.round((1 - rank) * (colours.scale.length - 1))]);
  const textOn = (fill, colours) => (luminance(fill) < .6 ? '#FFFFFF' : (colours.dark ? '#1F2A37' : colours.ink));

  const legend = (labels, fills, prefix = '') => `<div class="ni-finding-legend">${prefix ? `<span class="ni-finding-legend-prefix">${escapeHtml(prefix)}</span>` : ''}${
    labels.map((label, index) => `<span><i style="background:${fills[index]}"></i>${escapeHtml(label)}</span>`).join('')}</div>`;
  const stacked = (shares, fills, colours) => `<span class="ni-finding-stack">${shares.map((share, index) => (share > 0.05
    ? `<span style="flex:0 0 ${share}%;background:${fills[index]};color:${textOn(fills[index], colours)}" title="${Number(share).toFixed(1)}%">${share >= 4.5 ? Math.round(share) : ''}</span>`
    : '')).join('')}</span>`;

  const signalBody = (view, colours) => `<div class="ni-finding-signal">${view.panels.map(panel => `<section>
      <h4>${escapeHtml(panel.title)}</h4>
      ${panel.environments.map(block => `<div class="ni-finding-block"><p class="ni-finding-block-title">${escapeHtml(block.environment)}</p>
        ${block.rows.map(row => `<div class="ni-finding-row"><span class="ni-finding-label">${escapeHtml(row.group)}</span>${stacked(row.shares, colours.scale, colours)}</div>`).join('')}
      </div>`).join('')}
      ${legend(panel.classes, colours.scale)}
    </section>`).join('')}</div>`;

  const spreadBody = (view, colours, groupColours) => {
    const [spread, narrow] = view.panels;
    const shares = Object.fromEntries(narrow.rows.map(row => [row.group, row]));
    const maximum = Math.max(1, ...spread.rows.map(row => row.p90 || 0)) * 1.06;
    const narrowMaximum = Math.max(1, ...narrow.rows.map(row => row.share || 0));
    const position = value => `${(value || 0) / maximum * 100}%`;
    const label = row => `<span class="ni-finding-group" style="color:${groupColours[row.group] || 'inherit'}">${escapeHtml(row.group)}</span>`;
    return `<div class="ni-finding-spread">
      <section class="ni-finding-card"><h4>${escapeHtml(spread.title)}</h4>
        ${spread.rows.map(row => `<div class="ni-finding-spread-row">${label(row)}<span class="ni-finding-track">
          ${row.p10 !== null && row.p90 !== null ? `<span class="ni-finding-range" style="left:${position(row.p10)};width:calc(${position(row.p90)} - ${position(row.p10)})"></span>
          <span class="ni-finding-end is-low" style="right:calc(100% - ${position(row.p10)})">${row.p10}</span>
          <span class="ni-finding-end" style="left:${position(row.p90)}">${row.p90}</span>` : ''}
          ${row.median !== null ? `<span class="ni-finding-mark" style="left:${position(row.median)}"><b>${row.median}</b></span>` : ''}
        </span></div>`).join('')}
        <p class="ni-finding-note">${escapeHtml(spread.note || '')}</p></section>
      <section class="ni-finding-card"><h4>${escapeHtml(narrow.title)}</h4>
        ${spread.rows.map(row => {
          const figures = shares[row.group];
          if (!figures || figures.share === null) return `<div class="ni-finding-spread-row">${label(row)}<span></span></div>`;
          return `<div class="ni-finding-spread-row">${label(row)}<span class="ni-finding-bar"><span style="width:${figures.share / narrowMaximum * 82}%;background:${rankColour(colours, figures.rank)}"></span><b>${Number(figures.share).toFixed(1)}%</b></span></div>`;
        }).join('')}
        <p class="ni-finding-note">${escapeHtml(narrow.note || '')}</p></section>
    </div>`;
  };

  const sideCard = card => (card?.lines?.length ? `<aside class="ni-finding-card ni-finding-side"><h4>${escapeHtml(card.title)}</h4>
    ${card.lines.map(line => `<p><strong>${escapeHtml(line.lead)}</strong> ${escapeHtml(line.text)}</p>`).join('')}</aside>` : '');

  const barsBody = (view, fills, colours, side) => `${legend(view.classes, fills)}<div class="ni-finding-bars${side?.lines?.length ? ' has-side' : ''}" style="--ni-finding-panels:${view.panels.length}">
      ${view.panels.map(panel => `<section><h4>${escapeHtml(panel.title)}</h4>
        ${panel.rows.map(row => `<div class="ni-finding-row is-tall"><span class="ni-finding-label">${escapeHtml(row.group)}</span>${stacked(row.shares, fills, colours)}</div>`).join('')}
      </section>`).join('')}
      ${sideCard(side)}
    </div>`;

  const ladderBody = (view, colours, groupColours) => {
    const fills = ladderColours(colours, view.classes.length);
    const widest = Math.max(1, ...view.classes.map(item => item.width));
    const leader = view.columns.reduce((best, column) => ((column.wide_share || 0) > (best?.wide_share || 0) ? column : best), null);
    return `<div class="ni-finding-ladder">
      <div class="ni-finding-ladder-axis"><span>100%</span><span>50%</span><span>0%</span></div>
      <div class="ni-finding-ladder-plot">${view.columns.map(column => `<div class="ni-finding-ladder-column">
        <div class="ni-finding-ladder-stack">${column.shares.map((share, index) => (share > 0.05
          ? `<span style="height:${share}%;width:${view.classes[index].width / widest * 86}%;background:${fills[index]}" title="${escapeHtml(view.classes[index].label)}: ${Number(share).toFixed(1)}%"></span>` : '')).join('')}</div>
        <p><b style="color:${groupColours[column.group] || 'inherit'}">${escapeHtml(column.group)}</b> <span class="${column === leader ? 'is-leader' : ''}">${column.wide_share ?? '–'}% at 100 MHz+</span></p>
      </div>`).join('')}</div>
    </div>${legend(view.classes.map(item => item.label), fills, 'Width, MHz:')}<p class="ni-finding-note">${escapeHtml(view.note || '')}</p>`;
  };

  const body = (view, colours, groupColours) => {
    if (view.kind === 'signal') return signalBody(view, colours);
    if (view.kind === 'spread') return spreadBody(view, colours, groupColours);
    if (view.kind === 'technology') return barsBody(view, [colours.series[5], colours.scale[0]], colours, view.reading);
    if (view.kind === 'bands') return barsBody(view, colours.series.slice(0, view.classes.length), colours, view.side);
    if (view.kind === 'ladder') return ladderBody(view, colours, groupColours);
    return '';
  };

  const style = colours => [
    ['surface', colours.surface], ['ink', colours.ink], ['muted', colours.muted], ['accent', colours.accent],
    ['soft', colours.soft], ['line', colours.line], ['track', colours.track], ['title', colours.title],
    ['headline', colours.headline], ['title-weight', colours.titleWeight],
    ['title-transform', colours.titleCaps ? 'uppercase' : 'none'], ['headline-style', colours.headlineItalic ? 'italic' : 'normal'],
  ].map(([name, value]) => `--nit-${name}:${value}`).join(';') + (colours.font ? `;--nit-font:${colours.font}` : '')
    + (colours.titleFont ? `;--nit-title-font:${colours.titleFont}` : '');

  // Draw the views of ``findings`` in ``host``; ``scope`` (the filters of the analysis) ends each footnote.
  const render = (host, findings, theme, scope = '') => {
    if (!host) return;
    const views = findings?.views || [];
    if (!views.length) {
      host.innerHTML = '<p class="form-note">The selected CDRs have no Data tests for the Key Findings.</p>';
      return;
    }
    const colours = palette(theme);
    const groupColours = Object.fromEntries(Object.entries(findings.colours || {}).map(([group, colour]) => [group, colour ? hex(colour) : '']));
    host.innerHTML = views.map(view => `<article class="ni-finding" data-finding="${escapeHtml(view.key)}" style="${style(colours)}">
      <header class="ni-finding-head"><div><h3>${escapeHtml(view.title)}</h3><p class="ni-finding-headline">${escapeHtml(view.headline)}</p></div>
        ${view.tag ? `<span class="ni-finding-tag">${escapeHtml(view.tag)}</span>` : ''}</header>
      <div class="ni-finding-body">${body(view, colours, groupColours)}</div>
      <footer class="ni-finding-foot">
        ${view.basis ? `<p class="ni-finding-basis"><strong>Basis:</strong> ${escapeHtml(view.basis)}</p>` : ''}
        ${view.meaning ? `<p class="ni-finding-meaning"><strong>What it means:</strong> ${escapeHtml(view.meaning)}</p>` : ''}
        <p class="ni-finding-footnote">${escapeHtml([view.footnote, scope].filter(Boolean).join(' '))}</p>
      </footer>
    </article>`).join('');
  };

  window.NetworkInsightsFindings = {render, palette, ladderColours};
})();
