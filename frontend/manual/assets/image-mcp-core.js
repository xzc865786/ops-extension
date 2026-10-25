// Pure release validation, also loaded by the offline copy bundled in the installer.
(function (root) {
  'use strict';
  function validRelease(value) {
    return Boolean(value && value.schema === 1 && value.available === true
      && /^\d{1,4}\.\d{1,4}\.\d{1,6}$/.test(value.version)
      && /^assets\/downloads\/HuimaImageSetup-[A-Za-z0-9.-]+-win-x64\.exe$/.test(value.url)
      && /^[a-f0-9]{64}$/.test(value.sha256)
      && Number.isSafeInteger(value.bytes) && value.bytes > 0 && value.bytes < 2_000_000_000
      && ['unsigned-local', 'unsigned-preview', 'signed'].includes(value.signing));
  }
  root.HuimaImageManual = Object.freeze({validRelease});
})(globalThis);
