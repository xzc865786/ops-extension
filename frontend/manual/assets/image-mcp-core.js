// Pure download validation: independent of other manual sections.
(function (root) {
  'use strict';
  const labels = {windows_x64: 'Windows', macos_arm64: 'macOS ARM64', macos_x64: 'macOS x64'};
  function validDownload(value, platform) {
    if (!value || value.enabled !== true || !labels[platform]) return false;
    const url = value.download_url;
    if (typeof url !== 'string' || !/^(https:\/\/[A-Za-z0-9.-]+(:[0-9]{1,5})?(\/[A-Za-z0-9._~/-]*)?|assets\/downloads\/[A-Za-z0-9._-]{1,120}|\/ext\/api\/v1\/public\/manual-files\/[1-9][0-9]*\/[A-Za-z0-9._~%()+-]{1,600})$/.test(url)) return false;
    let name;
    try { name = decodeURIComponent(url.split('/').pop()); } catch { return false; }
    const extension = platform === 'windows_x64' ? /\.(exe|msi)$/i : /\.(dmg|pkg|zip)$/i;
    return Boolean(extension.test(name) && name === value.file_name && !/[\/\\\x00-\x1f]/.test(name)
      && /^\d{1,4}\.\d{1,4}\.\d{1,6}$/.test(value.version)
      && typeof value.system === 'string' && value.system.trim() && value.system.length <= 150
      && /^[a-f0-9]{64}$/.test(value.sha256)
      && Number.isSafeInteger(value.file_size) && value.file_size > 0 && value.file_size < 2_000_000_000
      && ['unsigned-preview', 'signed'].includes(value.signing));
  }
  function keyGuide(image) {
    const g = image?.recommended_group;
    const text = (value, max) => typeof value === 'string' && value.length <= max && !/[\x00-\x09\x0b-\x1f\x7f]/.test(value);
    const group = g && text(g.name, 64) && g.name.trim() && text(g.summary, 200) && text(g.notes, 500) ? g : null;
    const vendors = {anthropic:'Anthropic', openai:'OpenAI', gemini:'Gemini'};
    return {
      body: group ? `打开控制台的“API 密钥”页面，创建新密钥时选择「${group.name}」，再把生成的 API Key 填入汇码生图安装助手。`
        : '创建 API Key 时，请选择已开放生图模型的分组。具体分组见分组说明；不确定时联系客服。',
      detail: group ? [vendors[group.platform] ? `厂商选择：${vendors[group.platform]}` : '', group.summary, group.notes].filter(Boolean).join(' · ') : '',
      note: text(image?.key_note, 500) ? image.key_note : '',
    };
  }
  root.HuimaImageManual = Object.freeze({validDownload, keyGuide, labels});
})(globalThis);
