<script setup lang="ts">
import { computed, ref } from 'vue'
import api from '@/api/client'
import PatternList from '@/components/PatternList.vue'
import { useToast } from '@/composables/useToast'
import {
  CLIENTS, GROUP_BADGES, PLATFORM_LABELS, emptyGroup, findGroup, groupChanges, groupFromSub2API, syncGroup,
  type GroupInfo, type GroupsConfig, type Sub2APIGroup,
} from '@/utils/manualRules'

// Editor for the public "选择分组" page. Everything here is plain text on the manual.
const groups = defineModel<GroupsConfig>({ required: true })
const props = defineProps<{ errMsg: (e: any, fallback: string) => string }>()
const toast = useToast()

const open = ref<Set<number>>(new Set())
const toggle = (index: number) => {
  const next = new Set(open.value)
  if (next.has(index)) next.delete(index)
  else next.add(index)
  open.value = next
}

function move<T>(list: T[], index: number, delta: number) {
  const target = index + delta
  if (target < 0 || target >= list.length) return
  ;[list[index], list[target]] = [list[target], list[index]]
  if (list === (groups.value.items as unknown[])) {
    const next = new Set([...open.value].map((i) => (i === index ? target : i === target ? index : i)))
    open.value = next
  }
}

function addGroup() {
  groups.value.items.push(emptyGroup())
  open.value = new Set([...open.value, groups.value.items.length - 1])
}

function removeGroup(index: number) {
  const item = groups.value.items[index]
  if (!confirm(`删除分组“${item.name || '未命名'}”的说明？`)) return
  groups.value.items.splice(index, 1)
  open.value = new Set([...open.value].filter((i) => i !== index).map((i) => (i > index ? i - 1 : i)))
}

const lines = (event: Event) =>
  (event.target as HTMLTextAreaElement).value.split('\n').map((s) => s.trim()).filter(Boolean)

function setRate(item: GroupInfo, event: Event) {
  const value = (event.target as HTMLInputElement).value.trim()
  item.rate_multiplier = value === '' || Number.isNaN(Number(value)) ? null : Number(value)
}

function toggleClient(item: GroupInfo, key: GroupInfo['clients'][number], checked: boolean) {
  item.clients = CLIENTS.map((c) => c.key).filter((k) => (k === key ? checked : item.clients.includes(k)))
}

const platformOptions = (item: GroupInfo) => {
  const keys = Object.keys(PLATFORM_LABELS)
  return item.platform && !keys.includes(item.platform) ? [...keys, item.platform] : keys
}

// ---- Sub2API import ---------------------------------------------------------
const sync = ref<{ loading: boolean; error: string; list: Sub2APIGroup[]; picked: Set<number> } | null>(null)

const syncRows = computed(() =>
  (sync.value?.list || []).map((group) => {
    const item = findGroup(groups.value.items, group)
    return { group, item, changes: item ? groupChanges(item, group) : [] }
  }),
)

async function loadSub2API() {
  sync.value = { loading: true, error: '', list: [], picked: new Set() }
  try {
    const { data } = await api.get<Sub2APIGroup[]>('/admin/manual/sub2api-groups')
    sync.value.list = data
    // Preselect what needs attention: public groups not on the page yet, and entries that drifted.
    sync.value.picked = new Set(syncRows.value.filter((r) => (r.item ? r.changes.length : !r.group.is_exclusive)).map((r) => r.group.id))
  } catch (e: any) {
    sync.value.error = props.errMsg(e, '读取 Sub2API 分组失败')
  } finally {
    sync.value.loading = false
  }
}

function togglePick(id: number, checked: boolean) {
  if (!sync.value) return
  const next = new Set(sync.value.picked)
  if (checked) next.add(id)
  else next.delete(id)
  sync.value.picked = next
}

function applySync() {
  if (!sync.value) return
  let added = 0
  let updated = 0
  for (const row of syncRows.value) {
    if (!sync.value.picked.has(row.group.id)) continue
    if (row.item) {
      if (!row.changes.length) continue
      syncGroup(row.item, row.group)
      updated += 1
    } else if (groups.value.items.length < 30) {
      groups.value.items.push(groupFromSub2API(row.group))
      added += 1
    }
  }
  sync.value = null
  toast.push(added || updated ? `新增 ${added} 个、更新 ${updated} 个分组，补充说明后点“保存”生效` : '没有需要同步的分组')
}

function addFaq() {
  groups.value.faq.push({ q: '', a: '' })
}
</script>

<template>
  <div class="space-y-4">
    <section class="card p-5 sm:p-6 space-y-4">
      <h2 class="font-semibold">页面文字 <span class="muted text-sm font-normal">· 显示在手册“选择分组”页顶部</span></h2>
      <div>
        <label class="input-label" for="groups-intro">开头说明（纯文本，最多 500 字）</label>
        <textarea id="groups-intro" v-model="groups.intro" class="input" rows="3" maxlength="500"></textarea>
      </div>
      <div>
        <label class="input-label" for="groups-notice">黄色提示（留空则不显示，最多 300 字）</label>
        <textarea id="groups-notice" v-model="groups.notice" class="input" rows="2" maxlength="300" placeholder="例如：Claude 实惠分组 10 月 15 日起倍率调整为 0.9"></textarea>
      </div>
    </section>

    <section class="card p-5 sm:p-6 space-y-4">
      <div class="flex flex-wrap items-center justify-between gap-3">
        <h2 class="font-semibold">分组列表 <span class="muted text-sm font-normal">· 按这里的顺序显示，最多 30 个</span></h2>
        <div class="flex gap-2">
          <button type="button" class="btn-secondary btn-sm" :disabled="sync?.loading" @click="loadSub2API">{{ sync?.loading ? '读取中…' : '从 Sub2API 同步' }}</button>
          <button type="button" class="btn-primary btn-sm" :disabled="groups.items.length >= 30" @click="addGroup">新增分组</button>
        </div>
      </div>

      <div v-if="sync && !sync.loading" class="rounded-lg border border-slate-200 bg-slate-50 p-4 space-y-3">
        <div v-if="sync.error" class="alert-error" role="alert">{{ sync.error }}</div>
        <template v-else>
          <p class="text-sm">
            Sub2API 里有 {{ sync.list.length }} 个启用中的分组。勾选后：新分组会加到列表末尾（用 Sub2API 的描述作为介绍，默认显示）；
            已有分组只更新名称、倍率和 Key 风格，你写的说明不会被覆盖。
          </p>
          <div v-if="sync.list.length" class="table-wrap">
            <table class="table">
              <thead><tr><th></th><th>分组</th><th>风格</th><th>倍率</th><th>手册里</th></tr></thead>
              <tbody>
                <tr v-for="row in syncRows" :key="row.group.id">
                  <td><input type="checkbox" :checked="sync.picked.has(row.group.id)" :aria-label="`选择 ${row.group.name}`" @change="togglePick(row.group.id, ($event.target as HTMLInputElement).checked)" /></td>
                  <td>
                    {{ row.group.name }}
                    <span v-if="row.group.is_exclusive" class="badge badge-gray ml-1">专属</span>
                    <p v-if="row.group.description" class="muted text-xs">{{ row.group.description }}</p>
                  </td>
                  <td class="whitespace-nowrap text-sm">{{ PLATFORM_LABELS[row.group.platform] || row.group.platform }}</td>
                  <td class="whitespace-nowrap text-sm">
                    {{ row.group.rate_multiplier ?? '-' }}
                    <p v-if="row.group.peak" class="muted text-xs">高峰 {{ row.group.peak.start }}–{{ row.group.peak.end }} × {{ row.group.peak.multiplier }}</p>
                  </td>
                  <td class="text-sm">
                    <span v-if="!row.item" class="badge badge-primary">未添加</span>
                    <span v-else-if="!row.changes.length" class="badge badge-success">一致</span>
                    <span v-else class="text-amber-700">{{ row.changes.join('；') }}</span>
                  </td>
                </tr>
              </tbody>
            </table>
          </div>
          <p class="muted text-xs">专属分组只有开通的用户能选到，默认不勾选；需要公开时勾选后再决定是否“在手册显示”。</p>
        </template>
        <div class="flex gap-2">
          <button v-if="!sync.error && sync.list.length" type="button" class="btn-primary btn-sm" :disabled="!sync.picked.size" @click="applySync">同步选中的 {{ sync.picked.size }} 个</button>
          <button type="button" class="btn-ghost btn-sm" @click="sync = null">关闭</button>
        </div>
      </div>

      <p v-if="!groups.items.length" class="muted text-sm">还没有分组。手册会显示“分组说明正在整理中”，可以先从 Sub2API 同步。</p>

      <ol class="space-y-3">
        <li v-for="(item, index) in groups.items" :key="index" class="rounded-lg border border-slate-200 bg-white">
          <div class="flex flex-wrap items-center gap-2 px-4 py-3">
            <button type="button" class="flex min-w-0 flex-1 items-center gap-2 text-left" :aria-expanded="open.has(index)" @click="toggle(index)">
              <span class="text-xs text-slate-400">{{ open.has(index) ? '▾' : '▸' }} {{ index + 1 }}</span>
              <span class="truncate font-medium">{{ item.name || '未命名分组' }}</span>
              <span v-if="item.badge" class="badge badge-primary">{{ GROUP_BADGES.find((b) => b.key === item.badge)?.label }}</span>
              <span v-if="item.rate_multiplier !== null" class="muted text-sm">{{ item.rate_multiplier }}×</span>
              <span v-if="!item.visible" class="badge badge-gray">不显示</span>
              <span v-if="!item.sub2api_id" class="badge badge-warning">未关联 Sub2API</span>
            </button>
            <label class="flex items-center gap-1 text-sm"><input v-model="item.visible" type="checkbox" /> 在手册显示</label>
            <button type="button" class="btn-ghost btn-sm" :disabled="index === 0" aria-label="上移" @click="move(groups.items, index, -1)">↑</button>
            <button type="button" class="btn-ghost btn-sm" :disabled="index === groups.items.length - 1" aria-label="下移" @click="move(groups.items, index, 1)">↓</button>
            <button type="button" class="btn-ghost btn-sm text-red-600" @click="removeGroup(index)">删除</button>
          </div>

          <div v-if="open.has(index)" class="space-y-4 border-t border-slate-100 px-4 py-4">
            <div class="grid gap-4 sm:grid-cols-2">
              <div>
                <label class="input-label">分组名称（和 Sub2API 创建 Key 时看到的一致）</label>
                <input v-model.trim="item.name" class="input" maxlength="64" />
              </div>
              <div class="grid grid-cols-2 gap-3">
                <div>
                  <label class="input-label">标签</label>
                  <select v-model="item.badge" class="input">
                    <option v-for="b in GROUP_BADGES" :key="b.key" :value="b.key">{{ b.label }}</option>
                  </select>
                </div>
                <div>
                  <label class="input-label">Key 风格</label>
                  <select v-model="item.platform" class="input">
                    <option value="">不显示</option>
                    <option v-for="p in platformOptions(item)" :key="p" :value="p">{{ PLATFORM_LABELS[p] || p }}</option>
                  </select>
                </div>
              </div>
            </div>

            <div>
              <p class="input-label">适用软件（手册里按软件筛选时用）</p>
              <div class="flex flex-wrap gap-5 text-sm">
                <label v-for="c in CLIENTS" :key="c.key" class="flex items-center gap-2">
                  <input type="checkbox" :checked="item.clients.includes(c.key)" @change="toggleClient(item, c.key, ($event.target as HTMLInputElement).checked)" /> {{ c.label }}
                </label>
              </div>
              <p v-if="!item.clients.length" class="mt-1 text-xs text-amber-700">没有勾选时，只在“全部”里显示。</p>
            </div>

            <div class="grid gap-4 sm:grid-cols-[160px_minmax(0,1fr)]">
              <div>
                <label class="input-label">倍率（留空不显示数字）</label>
                <input :value="item.rate_multiplier ?? ''" type="number" min="0" max="1000" step="0.01" class="input" @input="setRate(item, $event)" />
              </div>
              <div>
                <label class="input-label">倍率说明（定性描述，最多 200 字）</label>
                <input v-model="item.billing_note" class="input" maxlength="200" placeholder="例如：性价比高，适合大量日常任务" />
              </div>
            </div>

            <div>
              <label class="input-label">一句话介绍（最多 200 字）</label>
              <textarea v-model="item.summary" class="input" rows="2" maxlength="200"></textarea>
            </div>

            <div class="grid gap-4 lg:grid-cols-2">
              <div>
                <label class="input-label">适合（每行一条，最多 8 条、每条 80 字）</label>
                <textarea :value="item.suitable_for.join('\n')" class="input" rows="4" placeholder="日常写代码&#10;长对话、读大项目" @change="item.suitable_for = lines($event).slice(0, 8)"></textarea>
              </div>
              <div>
                <p class="input-label">主要模型（模型 ID，可用 * 通配）</p>
                <PatternList v-model="item.models" ordered placeholder="例如 claude-sonnet-5-5" />
              </div>
            </div>

            <div>
              <label class="input-label">注意事项（可选，最多 500 字）</label>
              <textarea v-model="item.notes" class="input" rows="2" maxlength="500" placeholder="例如：高峰期可能需要排队"></textarea>
            </div>
          </div>
        </li>
      </ol>
    </section>

    <section class="card p-5 sm:p-6 space-y-4">
      <div class="flex items-center justify-between">
        <h2 class="font-semibold">常见问题 <span class="muted text-sm font-normal">· 最多 20 条</span></h2>
        <button type="button" class="btn-secondary btn-sm" :disabled="groups.faq.length >= 20" @click="addFaq">新增问题</button>
      </div>
      <p v-if="!groups.faq.length" class="muted text-sm">没有常见问题时，手册显示页面自带的默认问答。</p>
      <div v-for="(entry, index) in groups.faq" :key="index" class="grid gap-2 rounded-lg border border-slate-200 p-3 sm:grid-cols-[minmax(0,1fr)_auto]">
        <div class="space-y-2">
          <input v-model="entry.q" class="input" maxlength="100" placeholder="问题" />
          <textarea v-model="entry.a" class="input" rows="2" maxlength="500" placeholder="回答"></textarea>
        </div>
        <div class="flex gap-1 sm:flex-col">
          <button type="button" class="btn-ghost btn-sm" :disabled="index === 0" aria-label="上移" @click="move(groups.faq, index, -1)">↑</button>
          <button type="button" class="btn-ghost btn-sm" :disabled="index === groups.faq.length - 1" aria-label="下移" @click="move(groups.faq, index, 1)">↓</button>
          <button type="button" class="btn-ghost btn-sm text-red-600" @click="groups.faq.splice(index, 1)">删除</button>
        </div>
      </div>
    </section>
  </div>
</template>
