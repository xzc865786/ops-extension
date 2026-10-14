// Capability declarations describe the service actually routed by Huima, not just a model name.
// The WorkBuddy-wide switches are the defaults; a matching rule only overrides what it sets.
import {wildcard} from './ccswitch-setup-core.js';

const pick = (value, fallback) => typeof value === 'boolean' ? value : fallback;

export function resolveWorkBuddy(model, cfg) {
  const wb = cfg.workbuddy;
  const rules = wb.capability_rules || [];
  const exact = rules.find(rule => rule.models.some(pattern => pattern.toLowerCase() === model.toLowerCase()));
  const rule = exact || rules.find(item => item.models.some(pattern => wildcard(pattern).test(model)));
  const thinking = pick(rule?.supports_reasoning, wb.supports_reasoning);
  const canDisable = pick(rule?.can_disable_thinking, wb.can_disable_thinking === true);
  return {
    max_input_tokens: wb.max_input_tokens ?? null,
    max_output_tokens: wb.max_output_tokens ?? null,
    supports_tool_call: wb.supports_tool_call,
    supports_images: pick(rule?.supports_images, wb.supports_images),
    supports_reasoning: thinking,
    only_reasoning: thinking && !canDisable,
    default_effort: wb.default_effort || 'high',
    supported_efforts: wb.supported_efforts || ['low', 'medium', 'high'],
    can_disable_thinking: canDisable,
  };
}

export function workbuddySummary(model, cfg) {
  const options = resolveWorkBuddy(model, cfg);
  const labels = {low: '低', medium: '中', high: '高'};
  const thinking = options.supports_reasoning
    ? `默认开启思考：${labels[options.default_effort]}；可选 ${options.supported_efforts.map(effort => labels[effort]).join('／')}${options.only_reasoning ? '（仅思考模式，始终开启）' : ''}`
    : '该模型不开启思考';
  const image = options.supports_images ? '支持图片输入' : '仅支持文本输入';
  const limits = options.max_input_tokens === null && options.max_output_tokens === null
    ? '输入／输出上限使用 WorkBuddy 默认值' : '输入／输出上限按后台配置';
  return `${thinking}。${image}。${limits}。`;
}
