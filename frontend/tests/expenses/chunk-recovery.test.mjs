import assert from 'node:assert/strict'
import { test } from 'node:test'
import { readFileSync } from 'node:fs'
import ts from 'typescript'
const source = readFileSync(new URL('../../src/utils/chunkRecovery.ts', import.meta.url), 'utf8')
const js = ts.transpileModule(source, { compilerOptions: { target: ts.ScriptTarget.ES2022, module: ts.ModuleKind.ES2022 } }).outputText
const { isChunkLoadError, installChunkRecovery } = await import('data:text/javascript;base64,' + Buffer.from(js).toString('base64'))

test('recognizes browser module failures without treating business errors as a release failure', () => {
  for (const message of ['Failed to fetch dynamically imported module: /assets/page.js', 'Importing a module script failed.', 'error loading dynamically imported module', 'Unable to preload CSS for /assets/page.css']) {
    assert.equal(isChunkLoadError(new Error(message)), true)
  }
  for (const message of ['Request failed with status code 409', '付款人不能为空', 'Cannot read properties of undefined']) {
    assert.equal(isChunkLoadError(new Error(message)), false)
  }
})

test('failed Vite dependency raises a recoverable notice and listeners are removable', () => {
  const target = new EventTarget()
  let notices = 0
  const stop = installChunkRecovery(target, () => { notices++ })
  target.dispatchEvent(new Event('error', { cancelable: true }))
  assert.equal(notices, 0)
  const failure = new Event('vite:preloadError', { cancelable: true })
  target.dispatchEvent(failure)
  assert.equal(failure.defaultPrevented, true)
  assert.equal(notices, 1)
  stop()
  const after = new Event('vite:preloadError', { cancelable: true })
  target.dispatchEvent(after)
  assert.equal(after.defaultPrevented, false)
  assert.equal(notices, 1)
})
