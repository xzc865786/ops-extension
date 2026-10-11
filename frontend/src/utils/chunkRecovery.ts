// Preserve the open form on a deployment/network failure. Reload only on request.
export function isChunkLoadError(error: unknown): boolean {
  const message = error instanceof Error ? error.message : String(error)
  return /Failed to fetch dynamically imported module|Importing a module script failed|error loading dynamically imported module|Unable to preload CSS|Failed to load module script/i.test(message)
}

export function installChunkRecovery(target: EventTarget, notify: () => void): () => void {
  const handler = (event: Event) => {
    // Vite emits this event only for JS/CSS dependency loading failures.
    event.preventDefault()
    notify()
  }
  target.addEventListener('vite:preloadError', handler)
  return () => target.removeEventListener('vite:preloadError', handler)
}
