/* Windows / Mac switch. Loaded in <head> without defer so the other system's steps never flash. */
// Content marked data-os="windows" or data-os="mac" shows only for the chosen system. Nothing is stored.
(() => {
  'use strict';
  const root = document.documentElement;

  function detect() {
    const forced = new URLSearchParams(location.search).get('os');
    if (forced === 'mac' || forced === 'windows') return forced;
    const platform = (navigator.userAgentData && navigator.userAgentData.platform) || navigator.platform || '';
    return /mac/i.test(platform) || /Macintosh/.test(navigator.userAgent) ? 'mac' : 'windows';
  }

  function sync() {
    document.querySelectorAll('[data-os-choice]').forEach(button => {
      button.setAttribute('aria-pressed', String(button.dataset.osChoice === root.dataset.os));
    });
  }

  function choose(os) {
    if (os !== 'mac' && os !== 'windows') return;
    root.dataset.os = os;
    sync();
    document.dispatchEvent(new CustomEvent('huima:os', {detail: os}));
  }

  root.dataset.os = detect();
  document.addEventListener('click', event => {
    const button = event.target instanceof Element ? event.target.closest('[data-os-choice]') : null;
    if (button) choose(button.dataset.osChoice);
  });
  document.addEventListener('DOMContentLoaded', sync);
})();
