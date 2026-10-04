// Small shared helpers for the manual's interactive pages.

export function downloadUrl(url, name) {
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  document.body.append(link);
  link.click();
  link.remove();
}

export function download(text, name) {
  // cmd.exe can misparse UTF-8 batch files with LF-only lines. Keep the
  // downloaded script runnable even if a template was served with Unix lines.
  if (/\.cmd$/i.test(name)) text = text.replace(/\r\n|\r|\n/g, '\r\n');
  const url = URL.createObjectURL(new Blob([text], {type: 'application/octet-stream'}));
  downloadUrl(url, name);
  setTimeout(() => URL.revokeObjectURL(url), 30000);
}

// Run a click handler at most once at a time, then keep the button locked for a short cooldown,
// so repeated clicks cannot start duplicate downloads or open CC Switch several times.
// A handler returns false when it did nothing (e.g. a validation message), which unlocks at once.
export function guardClick(button, handler, cooldown = 2000) {
  button.addEventListener('click', async event => {
    if (button.dataset.busy) return;
    button.dataset.busy = 'true';
    button.disabled = true;
    let acted = true;
    try {
      acted = (await handler(event)) !== false;
    } finally {
      setTimeout(() => {
        delete button.dataset.busy;
        button.disabled = false;
      }, acted ? cooldown : 0);
    }
  });
}
