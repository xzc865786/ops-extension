// Fills groups.html with the admin-configured group list and FAQ. Text only: every value goes through
// textContent, so nothing the console saves can add markup or scripts to the page.
import {manualConfigReady} from './manual-config.js';
import {GROUP_BADGES, GROUP_CLIENTS, formatRate, groupsForClient, isSafeGroups, platformLabel} from './manual-config-core.js';

const byId = id => document.getElementById(id);

function el(tag, className = '', text) {
  const node = document.createElement(tag);
  if (className) node.className = className;
  if (text !== undefined) node.textContent = text;
  return node;
}

function groupCard(item) {
  const card = el('article', 'card group-card');
  const head = el('div', 'group-head');
  head.append(el('h3', '', item.name));
  if (item.badge) head.append(el('span', `badge group-badge ${item.badge}`, GROUP_BADGES[item.badge]));
  card.append(head);
  if (item.summary) card.append(el('p', 'group-summary', item.summary));

  const meta = el('dl', 'group-meta');
  const row = (label, ...values) => {
    const wrap = el('div');
    const value = el('dd');
    value.append(...values);
    wrap.append(el('dt', '', label), value);
    meta.append(wrap);
  };
  const clients = GROUP_CLIENTS.filter(client => item.clients.includes(client.key)).map(client => client.label);
  if (clients.length) row('适用软件', clients.join('、'));
  if (item.platform) row('Key 风格', platformLabel(item.platform));
  const rate = formatRate(item.rate_multiplier);
  if (rate || item.billing_note) {
    row(rate ? '倍率' : '计费', ...[rate && el('strong', 'group-rate', rate), item.billing_note && el('span', 'group-billing', item.billing_note)].filter(Boolean));
  }
  if (meta.children.length) card.append(meta);

  if (item.suitable_for.length) {
    const list = el('ul', 'group-uses');
    for (const entry of item.suitable_for) list.append(el('li', '', entry));
    card.append(el('p', 'group-label', '适合'), list);
  }
  if (item.models.length) {
    const list = el('div', 'group-models');
    for (const model of item.models) list.append(el('code', '', model));
    card.append(el('p', 'group-label', '主要模型'), list);
  }
  if (item.notes) card.append(el('p', 'group-notes', item.notes));
  return card;
}

function render(groups) {
  const intro = document.querySelector('[data-groups="intro"]');
  if (intro && groups.intro) intro.textContent = groups.intro;
  const notice = byId('groups-notice');
  if (notice) {
    notice.textContent = groups.notice;
    notice.hidden = !groups.notice;
  }

  const list = byId('group-list');
  const count = byId('group-count');
  const filter = byId('group-filter');
  const buttons = Array.from(document.querySelectorAll('[data-group-filter]'));
  if (list) {
    if (!groups.items.length) {
      if (filter) filter.hidden = true;
      if (count) count.hidden = true;
      const empty = el('div', 'notice');
      const link = el('a', '', '联系客服');
      link.href = 'index.html#contact';
      empty.append('分组说明正在整理中。创建 Key 时不确定选哪个分组，请先', link, '。');
      list.replaceChildren(empty);
    } else {
      const show = client => {
        const items = groupsForClient(groups.items, client);
        const label = GROUP_CLIENTS.find(entry => entry.key === client)?.label;
        for (const button of buttons) button.setAttribute('aria-pressed', String(button.dataset.groupFilter === client));
        if (count) {
          count.textContent = !label ? `共 ${items.length} 个分组`
            : items.length ? `适用 ${label} 的分组有 ${items.length} 个` : `暂时没有标注适用 ${label} 的分组，可以联系客服确认。`;
        }
        list.replaceChildren(...items.map(groupCard));
      };
      for (const button of buttons) button.addEventListener('click', () => show(button.dataset.groupFilter));
      if (filter) filter.hidden = false;
      show('all');
    }
  }

  const faq = byId('group-faq');
  if (faq && groups.faq.length) {
    faq.replaceChildren(...groups.faq.map(entry => {
      const details = el('details');
      details.append(el('summary', '', entry.q), el('p', 'group-answer', entry.a));
      return details;
    }));
  }
}

const cfg = await manualConfigReady.catch(() => null);
if (cfg && isSafeGroups(cfg.groups)) {
  if (document.readyState === 'loading') document.addEventListener('DOMContentLoaded', () => render(cfg.groups), {once: true});
  else render(cfg.groups);
} else {
  const list = byId('group-list');
  if (list) list.replaceChildren(el('div', 'notice warning', '分组说明加载失败，请刷新页面重试，或联系客服确认要选的分组。'));
}
