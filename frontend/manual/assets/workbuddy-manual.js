import {manualConfigReady} from './manual-config.js';
import {resolveWorkBuddy, workbuddySummary} from './workbuddy-config-core.js';

const cfg = await manualConfigReady.catch(() => null);
const model = document.getElementById('workbuddy-manual-model');
const summary = document.getElementById('workbuddy-manual-summary');
const labels = {low: '低', medium: '中', high: '高'};
function update() {
  if (!cfg) { summary.textContent = '配置加载失败，请刷新后查看推荐值。'; return; }
  const id = model.value.trim();
  const wb = resolveWorkBuddy(id, cfg);
  summary.textContent = workbuddySummary(id, cfg);
  const values = {
    tools: wb.supports_tool_call ? '勾选' : '不勾选',
    thinking: wb.supports_reasoning ? '勾选' : '不勾选',
    effort: wb.supports_reasoning ? labels[wb.default_effort] : '无需设置',
    efforts: wb.supports_reasoning ? wb.supported_efforts.map(value => labels[value]).join('、') : '无需设置',
    only: wb.only_reasoning ? '勾选' : '不勾选',
    disable: wb.supports_reasoning && wb.can_disable_thinking ? '勾选' : '不勾选',
    images: wb.supports_images ? '勾选' : '不勾选（仅支持文本）',
    input: wb.max_input_tokens ?? '留空，使用 WorkBuddy 默认值',
    output: wb.max_output_tokens ?? '留空，使用 WorkBuddy 默认值',
  };
  for (const cell of document.querySelectorAll('[data-wb-setting]')) cell.textContent = String(values[cell.dataset.wbSetting]);
}
model.addEventListener('input', update);
update();
