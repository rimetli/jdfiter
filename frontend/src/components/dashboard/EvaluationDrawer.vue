<script setup lang="ts">
defineProps<{ visible: boolean; loading: boolean; result: any; comment: string; submitting: boolean }>()
const emit = defineEmits<{
  "update:visible": [value: boolean]
  "update:comment": [value: string]
  decide: [value: string]
}>()

const levelText = (value: string | null) => ({ STRONGLY_RECOMMENDED: "强烈推荐", RECOMMENDED: "推荐", REVIEW: "待复核", LOW_MATCH: "低匹配" } as Record<string, string>)[value || ""] || "--"
const gateText = (value: string | null) => ({ PASSED: "门槛通过", REVIEW_REQUIRED: "需人工复核", NOT_MET: "门槛未达" } as Record<string, string>)[value || ""] || "--"
const decisionText = (value: string | null) => ({ ADVANCE: "进入面试", REJECT: "不通过", HOLD: "待定" } as Record<string, string>)[value || ""] || "--"
const decisionTagType = (value: string | null) => value === "ADVANCE" ? "success" : value === "REJECT" ? "danger" : "warning"
const dimensionName = (code: string) => ({ agent: "Agent能力", llm: "LLM应用", engineering: "软件工程", saas: "SaaS经验", industry: "行业匹配", growth: "成长潜力" } as Record<string, string>)[code] || code
const depthText = (value: string | null) => ({ DEEP: "深度实践", SHALLOW: "泛泛提及", NONE: "无证据" } as Record<string, string>)[value || ""] || ""
const roleText = (value: string | null) => ({ LEAD: "主导", CONTRIBUTOR: "参与", EXPOSURE: "了解" } as Record<string, string>)[value || ""] || ""
</script>

<template>
  <el-drawer :model-value="visible" title="候选人评估报告" size="min(860px, 96vw)" @update:model-value="emit('update:visible', $event)">
    <div v-loading="loading" class="result-panel"><template v-if="result">
      <section class="result-identity"><div><p class="eyebrow">简历</p><h3>{{ result.filename || `申请 #${result.application_id}` }}</h3></div><div class="result-identity-meta"><el-tag v-if="result.requirement_version_no" effect="plain">模型 V{{ result.requirement_version_no }}</el-tag><el-tag v-if="result.human_decision" :type="decisionTagType(result.human_decision.decision)">已决策：{{ decisionText(result.human_decision.decision) }}</el-tag></div></section>
      <section class="result-hero"><div class="result-score">{{ result.score }}</div><div><p class="eyebrow">综合评分 / 100</p><h2>{{ levelText(result.level) }}</h2><p class="muted">门槛：{{ gateText(result.gate_result) }} · 置信度：{{ (result.confidence * 100).toFixed(0) }}%</p></div></section>
      <section class="result-summary"><div><strong>优势</strong><p v-for="item in result.summary.advantages || []" :key="item">{{ item }}</p></div><div><strong>风险</strong><p v-for="item in result.summary.risks || []" :key="item">{{ item }}</p></div><div><strong>待确认</strong><p v-for="item in result.summary.unknowns || []" :key="item">{{ item }}</p></div></section>
      <section class="result-details"><article v-for="detail in result.details" :key="detail.id" class="result-detail-card" :class="{ 'is-unknown': detail.status === 'UNKNOWN' }"><div class="dimension-title"><div><strong>{{ dimensionName(detail.dimension_code) }}</strong><el-tag :type="detail.status === 'MET' ? 'success' : detail.status === 'NOT_MET' ? 'danger' : detail.status === 'UNKNOWN' ? 'warning' : 'info'" effect="plain">{{ detail.status === "MET" ? "满足" : detail.status === "PARTIAL" ? "部分满足" : detail.status === "UNKNOWN" ? "证据不足" : "不满足" }}</el-tag><el-tag v-if="detail.depth && (detail.status === 'MET' || detail.status === 'PARTIAL')" :type="detail.depth === 'DEEP' ? 'success' : 'warning'" effect="plain">{{ depthText(detail.depth) }}<template v-if="detail.role"> · {{ roleText(detail.role) }}</template></el-tag></div><span>{{ detail.score }} / {{ detail.max_score }}</span></div><p>{{ detail.reason }}</p><blockquote v-for="evidence in detail.evidence" :key="evidence.quote">{{ evidence.quote }}</blockquote></article></section>
      <section class="decision-panel"><p class="eyebrow">人工决策</p><el-input :model-value="comment" type="textarea" :rows="2" placeholder="决策备注（可选）" @update:model-value="emit('update:comment', $event)" /><div class="decision-buttons"><el-button type="success" :loading="submitting" @click="emit('decide', 'ADVANCE')">进入面试</el-button><el-button type="warning" :loading="submitting" @click="emit('decide', 'HOLD')">待定</el-button><el-button type="danger" :loading="submitting" @click="emit('decide', 'REJECT')">不通过</el-button></div></section>
      <p class="model-note">模型：{{ result.model }} · Prompt：{{ result.prompt_version }} · 规则：{{ result.rubric_version }}</p>
    </template></div>
  </el-drawer>
</template>
