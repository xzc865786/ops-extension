// Helper for .github/workflows/manual-macos.yml: builds the exact commands the manual page would show
// (pointing at this checkout through file:// URLs) and checks what the scripts wrote. Not a node:test file.
// Usage: node frontend/tests/manual/mac-ci.mjs config-command | restore-command | seed | verify | verify-restored
import assert from 'node:assert/strict';
import {existsSync, mkdirSync, readFileSync, readdirSync, statSync, writeFileSync} from 'node:fs';
import {homedir} from 'node:os';
import {join} from 'node:path';

import {buildMacConfigCommand, buildMacRestoreCommand} from '../../manual/assets/mac-command-core.js';

const DEFAULTS = JSON.parse(readFileSync(new URL('../../manual/assets/manual-config.default.json', import.meta.url), 'utf8'));
const PAGE = new URL('../../manual/quick.html', import.meta.url).href;
const HOME = homedir();
const file = (...parts) => join(HOME, ...parts);
const read = path => readFileSync(path, 'utf8');
const SEED_SETTINGS = '{"theme":"dark","env":{"ANTHROPIC_API_KEY":"old-key","HTTP_PROXY":"http://proxy"}}\n';
const SEED_TOML = 'approval_policy = "never"\n';
// Real keys come from repository secrets when present; otherwise placeholders exercise the file handling only.
const claudeKey = process.env.HUIMA_TEST_CLAUDE_KEY || 'sk-ci-claude-placeholder';
const codexKey = process.env.HUIMA_TEST_CODEX_KEY || 'sk-ci-codex-placeholder';
const claudeModel = process.env.HUIMA_TEST_CLAUDE_MODEL || 'claude-sonnet-5-5';
const codexModel = process.env.HUIMA_TEST_CODEX_MODEL || 'gpt-6.1-sol';

const actions = {
  'config-command': () => console.log(buildMacConfigCommand({
    claude: {apiKey: claudeKey, model: claudeModel, roles: {haiku: claudeModel}},
    codex: {apiKey: codexKey, model: codexModel},
    workbuddy: {apiKey: codexKey, model: codexModel},
  }, DEFAULTS, PAGE).command),
  'restore-command': () => console.log(buildMacRestoreCommand(PAGE)),
  seed: () => {
    mkdirSync(file('.claude'), {recursive: true});
    mkdirSync(file('.codex'), {recursive: true});
    writeFileSync(file('.claude', 'settings.json'), SEED_SETTINGS);
    writeFileSync(file('.codex', 'config.toml'), SEED_TOML);
  },
  verify: () => {
    const settings = JSON.parse(read(file('.claude', 'settings.json')));
    assert.equal(settings.theme, 'dark', 'unrelated Claude settings are kept');
    assert.equal(settings.env.HTTP_PROXY, 'http://proxy');
    assert.equal(settings.env.ANTHROPIC_API_KEY, undefined);
    assert.equal(settings.env.ANTHROPIC_AUTH_TOKEN, claudeKey);
    assert.equal(settings.env.ANTHROPIC_BASE_URL, 'https://api.tysy.top');
    assert.equal(settings.model, claudeModel);
    assert.equal(JSON.parse(read(file('.claude.json'))).hasCompletedOnboarding, true);
    const toml = read(file('.codex', 'config.toml'));
    assert.match(toml, /^model_provider = "huima"$/m);
    assert.match(toml, /^approval_policy = "never"$/m);
    assert.match(toml, /^base_url = "https:\/\/api\.tysy\.top\/v1"$/m);
    assert.equal(JSON.parse(read(file('.codex', 'auth.json'))).OPENAI_API_KEY, codexKey);
    const models = JSON.parse(read(file('.workbuddy', 'models.json')));
    assert.equal(models[0].url, 'https://api.tysy.top/v1/chat/completions');
    for (const path of [file('.claude', 'settings.json'), file('.codex', 'auth.json'), file('.workbuddy', 'models.json')]) {
      assert.equal(statSync(path).mode & 0o077, 0, `${path} must be private`);
    }
    const backups = readdirSync(file('.huima', 'backups'));
    assert.equal(backups.length, 1);
    const manifest = JSON.parse(read(file('.huima', 'backups', backups[0], 'manifest.json')));
    assert.equal(manifest.status, 'active');
    assert.equal(manifest.files.length, 5);
    console.log('configuration verified');
  },
  'verify-restored': () => {
    assert.equal(read(file('.claude', 'settings.json')), SEED_SETTINGS);
    assert.equal(read(file('.codex', 'config.toml')), SEED_TOML);
    for (const gone of [file('.claude.json'), file('.codex', 'auth.json'), file('.workbuddy', 'models.json')]) {
      assert.equal(existsSync(gone), false, `${gone} did not exist before and must be removed`);
    }
    const [backup] = readdirSync(file('.huima', 'backups'));
    assert.equal(JSON.parse(read(file('.huima', 'backups', backup, 'manifest.json'))).status, 'restored');
    console.log('restore verified');
  },
};

const action = actions[process.argv[2]];
if (!action) throw new Error(`unknown action: ${process.argv[2]}`);
action();
