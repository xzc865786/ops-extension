<script setup lang="ts">
import { computed } from 'vue'
import { PLATFORM_LABELS } from '@/utils/manualRules'
const model = defineModel<any>({ required: true })
const props = defineProps<{files: any[]; groups: any[]}>()
const platforms = [{key:'windows_x64', label:'Windows x64'}, {key:'macos_arm64', label:'macOS ARM64'}, {key:'macos_x64', label:'macOS x64'}]
const candidates = computed(() => props.groups.filter(g => g.visible && g.sub2api_id && props.groups.filter(item => item.sub2api_id === g.sub2api_id).length === 1))
const selected = computed(() => props.groups.find(g => g.sub2api_id === model.value.recommended_group_id))
const fileFor = (item: any) => props.files.find(f => f.id === item.file_id)
const numberValue = (event: Event) => (event.target as HTMLInputElement).value === '' ? null : Number((event.target as HTMLInputElement).value)
const size = (bytes: number) => `${(bytes / 1048576).toFixed(1)} MiB`
</script>

<template>
  <div class="space-y-4">
    <p class="muted text-sm">汇码生图安装包与推荐分组随本次配置一起发布，约 1 分钟后生效。Mac 仅预留配置，没有实际安装包时请保持关闭。</p>
    <section v-for="p in platforms" :key="p.key" class="card p-5 sm:p-6 space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-2"><h2 class="font-semibold">{{ p.label }} 安装包</h2><label class="flex items-center gap-2 text-sm"><input v-model="model.downloads[p.key].enabled" type="checkbox" /> 开放下载</label></div>
      <div class="grid gap-4 sm:grid-cols-2">
        <div><label class="input-label">下载来源</label><select v-model="model.downloads[p.key].source" class="input"><option value="url">填写下载地址</option><option value="file">使用文件库</option></select></div>
        <div><label class="input-label">版本号</label><input v-model.trim="model.downloads[p.key].version" class="input" placeholder="0.1.0" /></div>
        <div><label class="input-label">适用系统说明</label><input v-model.trim="model.downloads[p.key].system" class="input" maxlength="150" :placeholder="p.key === 'windows_x64' ? 'Windows 10 1809 及以上 · 64 位' : p.key === 'macos_arm64' ? 'macOS · Apple Silicon' : 'macOS · Intel'" /></div>
        <div><label class="input-label">签名状态</label><select v-model="model.downloads[p.key].signing" class="input"><option value="unsigned-preview">未签名预览版</option><option value="signed">已签名</option><option value="unsigned-local">本地测试构建（不可开放下载）</option></select></div>
      </div>
      <template v-if="model.downloads[p.key].source === 'url'">
        <div><label class="input-label">下载地址（https、assets/downloads/ 或站内手册文件地址）</label><input v-model.trim="model.downloads[p.key].url" class="input" /></div>
        <div class="grid gap-4 sm:grid-cols-2">
          <div><label class="input-label">文件名（须与地址一致）</label><input v-model.trim="model.downloads[p.key].file_name" class="input" /></div>
          <div><label class="input-label">文件大小（字节）</label><input :value="model.downloads[p.key].file_size" @input="model.downloads[p.key].file_size = numberValue($event)" class="input" type="number" min="1" /></div>
        </div>
        <div><label class="input-label">SHA-256</label><input v-model.trim="model.downloads[p.key].sha256" class="input font-mono" /></div>
        <p class="muted text-xs">外部地址须允许浏览器 HEAD 请求并公开 Content-Length；保存配置不会抓取外部地址。站内文件的元数据始终取自服务端记录。</p>
      </template>
      <template v-else>
        <div><label class="input-label">选择已上传的安装包</label><select v-model="model.downloads[p.key].file_id" class="input"><option :value="null">请选择文件</option><option v-for="f in files" :key="f.id" :value="f.id">{{ f.file_name }}（{{ size(f.file_size) }}）</option></select></div>
        <div v-if="fileFor(model.downloads[p.key])" class="rounded-lg bg-slate-50 p-3 text-sm break-all">
          <p>{{ fileFor(model.downloads[p.key]).file_name }} · {{ size(fileFor(model.downloads[p.key]).file_size) }}</p><p>SHA-256：{{ fileFor(model.downloads[p.key]).sha256 }}</p>
        </div>
        <p class="muted text-xs">文件名、大小和 SHA-256 由服务端文件记录提供。请在下方共用文件库上传、删除文件。</p>
      </template>
      <div><label class="input-label">补充提示（可留空）</label><textarea v-model="model.downloads[p.key].note" class="input" maxlength="500" rows="2"></textarea></div>
      <p class="text-sm">预览：{{ model.downloads[p.key].enabled ? `下载汇码生图安装包（${p.key === 'windows_x64' ? 'Windows' : p.label}）` : '下载已暂停' }}<template v-if="model.downloads[p.key].enabled"> · {{ model.downloads[p.key].system }} · v{{ model.downloads[p.key].version }} · {{ model.downloads[p.key].signing === 'signed' ? '已签名' : '未签名预览版' }}</template></p>
    </section>
    <section class="card p-5 sm:p-6 space-y-4">
      <h2 class="font-semibold">生图分组</h2>
      <div><label class="input-label">推荐分组</label><select v-model="model.recommended_group_id" class="input"><option :value="null">不指定，显示通用指引</option><option v-for="g in candidates" :key="g.sub2api_id" :value="g.sub2api_id">{{ g.name }}（{{ PLATFORM_LABELS[g.platform] || g.platform || '未填写厂商' }}）</option></select></div>
      <p class="muted text-xs">仅可选择唯一关联 Sub2API、且在手册公开显示的条目。请先在“分组说明”中关联分组；名称和说明始终取自同一条目。</p>
      <p v-if="model.recommended_group_id && !candidates.some(g => g.sub2api_id === model.recommended_group_id)" class="text-red-600 text-sm">当前推荐分组已删除、隐藏或重复关联，请重新选择或取消推荐后再保存。</p>
      <div v-if="selected" class="rounded-lg bg-slate-50 p-3 text-sm whitespace-pre-line"><strong>{{ selected.name }}</strong><p>{{ PLATFORM_LABELS[selected.platform] || selected.platform }}</p><p>{{ selected.summary }}</p><p>{{ selected.notes }}</p></div>
      <div><label class="input-label">Key 补充说明（例如开通条件，可留空）</label><textarea v-model="model.key_note" class="input" maxlength="500" rows="3"></textarea></div>
      <h3 class="font-semibold">创建一把用于生图的 API Key</h3>
      <p class="text-sm">{{ selected ? `打开控制台的“API 密钥”页面，创建新密钥时选择「${selected.name}」，再把生成的 API Key 填入汇码生图安装助手。` : '创建 API Key 时，请选择已开放生图模型的分组。具体分组见分组说明；不确定时联系客服。' }}</p><p class="text-sm whitespace-pre-line">{{ model.key_note }}</p>
      <p class="muted text-xs">推荐仅为使用指引，不表示已验证 Key 权限。生图 Key 填入生图安装助手，原有聊天软件的 Key 无需替换。</p>
    </section>
  </div>
</template>
