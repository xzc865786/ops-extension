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
  async function loadRelease() {
    if (location.protocol === 'file:') {
      download.textContent = '你正在阅读随包手册';
      status.textContent = '无需重复下载，重新打开安装助手即可管理配置。';
      return;
    }
    try {
      const response = await fetch('assets/image-mcp-release.json', {credentials: 'omit', redirect: 'error', cache: 'no-store'});
      if (!response.ok) throw new Error('Release unavailable');
      const release = await response.json();
      if (!globalThis.HuimaImageManual.validRelease(release)) throw new Error('Release not ready');
      const file = await fetch(release.url, {method: 'HEAD', credentials: 'omit', redirect: 'error', cache: 'no-store'});
      if (!file.ok || Number(file.headers.get('Content-Length')) !== release.bytes) throw new Error('Package unavailable');
      download.href = release.url; download.download = release.url.split('/').pop(); download.removeAttribute('aria-disabled'); download.textContent = '下载 Windows 安装助手';
      status.textContent = `v${release.version} · Windows x64 · ${(release.bytes / 1048576).toFixed(1)} MiB${release.signing === 'unsigned-preview' ? ' · 未签名预览版' : ''}`;
      document.getElementById('image-release-meta').textContent = `版本 ${release.version}，适用于 Windows 10 1809 或更新的 64 位 Windows。`;
      document.getElementById('image-release-sha').textContent = release.sha256;
      document.getElementById('image-signing-note').textContent = release.signing === 'signed'
        ? '下载后可在文件属性中查看数字签名，并核对发布者。'
        : release.signing === 'unsigned-preview'
          ? '未签名预览版：尚无可信发布者数字签名，Windows 可能提示未知发布者或阻止运行。请确认下载来源，并核对下方 SHA-256；如不确定，请等待签名版。'
          : '此包为本地测试构建，尚未进行代码签名，不作为公开发行包。';
      document.getElementById('image-release-details').hidden = false;
    } catch {
      download.removeAttribute('href'); download.setAttribute('aria-disabled', 'true'); download.textContent = '安装包准备中';
      status.textContent = '当前没有可下载的完整安装包，请稍后查看或联系客服。';
    }
  }
  loadRelease();
})();
