<script setup lang="ts">
import { reactive, watch } from "vue"

const props = defineProps<{ visible: boolean; loading: boolean; candidate: any; feedbacks: any[]; submitting: boolean }>()
const emit = defineEmits<{
  "update:visible": [value: boolean]
  submit: [value: { round_name: string; result: string; dimension_feedback: Record<string, string>; comment: string }]
}>()

const form = reactive({ round_name: "一面", result: "ADVANCE", communication: "", professional: "", culture: "", comment: "" })
watch(() => props.visible, (visible) => {
  if (visible) Object.assign(form, { round_name: "一面", result: "ADVANCE", communication: "", professional: "", culture: "", comment: "" })
})
const resultText = (value: string) => ({ ADVANCE: "建议进入下一轮", HOLD: "待定", REJECT: "不建议通过" } as Record<string, string>)[value] || value
const tagType = (value: string) => value === "ADVANCE" ? "success" : value === "REJECT" ? "danger" : "warning"
const formatDateTime = (value?: string | null) => {
  if (!value) return "--"
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return value.replace("T", " ").slice(0, 19)
  const pad = (number: number) => String(number).padStart(2, "0")
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())} ${pad(date.getHours())}:${pad(date.getMinutes())}:${pad(date.getSeconds())}`
}
function submit() {
  if (!form.round_name.trim()) return
  const dimension_feedback = Object.fromEntries(Object.entries({ 沟通表达: form.communication, 专业能力: form.professional, 团队契合: form.culture }).filter(([, value]) => value.trim()))
  emit("submit", { round_name: form.round_name.trim(), result: form.result, dimension_feedback, comment: form.comment.trim() })
}
</script>

<template>
  <el-drawer :model-value="visible" title="面试评价" size="min(680px, 96vw)" @update:model-value="emit('update:visible', $event)">
    <div v-loading="loading" class="feedback-panel">
      <template v-if="candidate">
        <p class="eyebrow">候选人简历</p><h3>{{ candidate.filename }}</h3>
        <el-form label-position="top" class="feedback-form" @submit.prevent="submit">
          <div class="feedback-grid">
            <el-form-item label="面试轮次" required><el-input v-model="form.round_name" maxlength="100" placeholder="例如：一面、HR 面" /></el-form-item>
            <el-form-item label="面试结论" required><el-select v-model="form.result"><el-option label="建议进入下一轮" value="ADVANCE" /><el-option label="待定" value="HOLD" /><el-option label="不建议通过" value="REJECT" /></el-select></el-form-item>
          </div>
          <el-form-item label="沟通表达"><el-input v-model="form.communication" placeholder="可选，例如：表达清晰，能结构化说明项目" /></el-form-item>
          <el-form-item label="专业能力"><el-input v-model="form.professional" placeholder="可选，例如：对 Agent 工程化经验扎实" /></el-form-item>
          <el-form-item label="团队契合"><el-input v-model="form.culture" placeholder="可选，例如：主动性强，协作方式契合" /></el-form-item>
          <el-form-item label="面试评价"><el-input v-model="form.comment" type="textarea" :rows="4" maxlength="5000" show-word-limit placeholder="记录关键问答、亮点、风险与后续建议" /></el-form-item>
          <el-button type="primary" native-type="submit" :loading="submitting" :disabled="!form.round_name.trim()">保存面试评价</el-button>
        </el-form>
        <section class="feedback-history"><p class="eyebrow">历史评价（{{ feedbacks.length }}）</p>
          <el-empty v-if="!feedbacks.length" description="尚未记录面试评价" :image-size="80" />
          <article v-for="item in feedbacks" :key="item.id" class="feedback-card"><div class="feedback-head"><strong>{{ item.round_name }}</strong><el-tag :type="tagType(item.result)" effect="plain">{{ resultText(item.result) }}</el-tag></div><p v-if="item.comment">{{ item.comment }}</p><dl v-if="Object.keys(item.dimension_feedback || {}).length"><template v-for="(value, label) in item.dimension_feedback" :key="label"><dt>{{ label }}</dt><dd>{{ value }}</dd></template></dl><small>{{ item.interviewer_name }} · {{ formatDateTime(item.created_at) }}</small></article>
        </section>
      </template>
    </div>
  </el-drawer>
</template>

<style scoped>
.feedback-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 0 14px; }
.feedback-history { margin-top: 28px; border-top: 1px solid var(--el-border-color-lighter); padding-top: 20px; }
.feedback-card { border: 1px solid var(--el-border-color-lighter); border-radius: 10px; padding: 14px; margin: 10px 0; }
.feedback-head { display: flex; justify-content: space-between; gap: 12px; align-items: center; }
.feedback-card p { white-space: pre-wrap; line-height: 1.6; margin: 10px 0; }
.feedback-card dl { display: grid; grid-template-columns: 90px 1fr; gap: 5px 10px; margin: 8px 0; font-size: 13px; }
.feedback-card dt { color: var(--el-text-color-secondary); }.feedback-card dd { margin: 0; }.feedback-card small { color: var(--el-text-color-secondary); }
@media (max-width: 560px) { .feedback-grid { grid-template-columns: 1fr; } }
</style>
