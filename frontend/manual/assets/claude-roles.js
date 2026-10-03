// Shared UI for the Claude Code role-model selects (fable / opus / sonnet / haiku / subagent).
import {CLAUDE_ROLES, suggestClaudeRoles} from './ccswitch-setup-core.js';

const ROLES = Object.keys(CLAUDE_ROLES);
const select = (prefix, role) => document.getElementById(`${prefix}${role}`);

export function resetRoleSelects(prefix) {
  for (const role of ROLES) {
    const element = select(prefix, role);
    element.replaceChildren(new Option('读取模型后自动选择', ''));
    element.disabled = true;
  }
}

export function fillRoleSelects(prefix, ids, main) {
  const suggested = suggestClaudeRoles(ids, main);
  for (const role of ROLES) {
    const element = select(prefix, role);
    const options = ids.map(id => new Option(id, id));
    if (role === 'subagent') options.unshift(new Option('跟随默认（推荐）', ''));
    element.replaceChildren(...options);
    element.value = suggested[role];
    element.disabled = false;
  }
}

export function readRoleSelects(prefix) {
  return Object.fromEntries(ROLES.map(role => [role, select(prefix, role).value]));
}
