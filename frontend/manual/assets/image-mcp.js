(function () {
  'use strict';
  const instructions = {
    workbuddy: '完全退出并重新打开 WorkBuddy。进入“专家·技能·连接器” → “连接器” → “自定义连接器”，在 MCP 服务管理中检查 huima-image。按提示信任后，确认连接正常、3/3 工具启用，再新建聊天并发送指令。',
    codex: '完全退出 Codex，重新打开并新建聊天，再粘贴指令发送。停止聊天不一定取消生图请求，超时后先核对图片和使用记录。',
    claude: '重新启动已配置的 Claude Code 会话，再粘贴指令发送。出现工具授权提示时，核对汇码生图工具和本次操作后再决定是否允许。',
  };
  document.querySelectorAll('[data-image-client]').forEach(button => {
    button.addEventListener('click', () => {
      document.querySelectorAll('[data-image-client]').forEach(item => item.setAttribute('aria-pressed', String(item === button)));
      document.getElementById('image-client-instruction').textContent = instructions[button.dataset.imageClient];
    });
  });
  const download = document.getElementById('image-download');
  const status = document.getElementById('image-release-status');
  download.addEventListener('click', event => { if (download.getAttribute('aria-disabled') === 'true') event.preventDefault(); });
  function disable(message) {
    download.removeAttribute('href'); download.setAttribute('aria-disabled', 'true');
    download.textContent = '安装包暂不可下载'; status.textContent = message;
    document.getElementById('image-release-details').hidden = true;
  }
  let generation = 0;
  async function showDownload(item, platform) {
    const current = ++generation;
    disable('正在检查安装包是否可用…');
    if (!item?.enabled) { disable(item?.unavailable_reason || '管理员已暂停此系统的安装包下载。'); return; }
    if (!globalThis.HuimaImageManual.validDownload(item, platform)) { disable('安装包发行信息不完整，请联系客服。'); return; }
    try {
      const file = await fetch(item.download_url, {method:'HEAD', credentials:'omit', redirect:'error', cache:'no-store', signal:AbortSignal.timeout(10000)});
      if (current !== generation) return;
      if (!file.ok || Number(file.headers.get('Content-Length')) !== item.file_size) throw new Error();
      download.href = item.download_url; download.download = item.file_name;
      download.removeAttribute('aria-disabled');
      download.textContent = `下载汇码生图安装包（${globalThis.HuimaImageManual.labels[platform]}）`;
      const signing = item.signing === 'signed' ? '已签名' : '未签名预览版';
      status.textContent = `${item.system} · v${item.version} · ${(item.file_size / 1048576).toFixed(1)} MiB · ${signing}`;
      document.getElementById('image-release-meta').textContent = `${item.file_name} · ${status.textContent}${item.note ? ' · ' + item.note : ''}`;
      document.getElementById('image-release-sha').textContent = item.sha256;
      document.getElementById('image-signing-note').textContent = item.signing === 'signed'
        ? '下载后可在文件属性中查看数字签名，并核对发布者。'
        : '未签名预览版：尚无可信发布者数字签名，Windows 可能提示未知发布者或阻止运行。请确认下载来源，并核对上方 SHA-256；如不确定，请等待签名版。';
      document.getElementById('image-release-details').hidden = false;
    } catch {
      if (current === generation) disable('安装包文件不可用或无法核对文件大小，请稍后重试或联系客服。');
    }
  }
  async function loadRelease() {
    if (location.protocol === 'file:') {
      download.textContent = '你正在阅读随包手册';
      status.textContent = '无需重复下载，重新打开安装助手即可管理配置。离线手册随安装包维护，不会随网站自动更新。';
      return;
    }
    try {
      const {manualConfigState} = await import('./manual-config.js');
      const {config, source} = await manualConfigState;
      if (source !== 'api') { disable('下载配置加载失败，请刷新页面或联系客服。正文教程仍可阅读。'); return; }
      const image = config.image_mcp;
      const guide = globalThis.HuimaImageManual.keyGuide(image);
      document.getElementById('image-key-guide').textContent = guide.body;
      document.getElementById('image-key-detail').textContent = guide.detail;
      document.getElementById('image-key-note').textContent = guide.note;
      const downloads = image?.downloads;
      if (!downloads) { disable('安装包配置不可用，请联系客服。'); return; }
      const platforms = Object.keys(globalThis.HuimaImageManual.labels);
      const ready = platforms.filter(key => globalThis.HuimaImageManual.validDownload(downloads[key], key));
      const select = document.getElementById('image-platform');
      if (ready.length > 1) {
        for (const key of ready) {
          const option = document.createElement('option'); option.value = key; option.textContent = globalThis.HuimaImageManual.labels[key]; select.append(option);
        }
        document.getElementById('image-platform-control').hidden = false;
        select.addEventListener('change', () => showDownload(downloads[select.value], select.value));
      }
      const only = ready.length === 1 ? ready[0] : 'windows_x64';
      const mac = /Mac|iPhone|iPad/.test([navigator.platform, navigator.userAgent].join(' '));
      const preferred = ready.find(key => mac ? key.startsWith('macos') : key === 'windows_x64') || only;
      select.value = preferred;
      document.getElementById('image-platform-note').textContent = ready.length === 1 && only === 'windows_x64'
        ? '当前仅提供 Windows x64 安装包，Mac 暂无安装包。' : '';
      if (mac && !ready.some(key => key.startsWith('macos'))) { disable('当前仅提供 Windows x64 安装包，Mac 暂无可用安装包。'); return; }
      await showDownload(downloads[preferred], preferred);
    } catch { disable('下载配置加载失败，请刷新页面或联系客服。正文教程仍可阅读。'); }
  }
  loadRelease();
})();
