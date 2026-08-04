<script setup lang="ts">
import { computed, defineAsyncComponent, onMounted, reactive, ref } from "vue"
import { ElMessage, ElMessageBox } from "element-plus"
import { useRouter } from "vue-router"

import { api } from "../api/client"

const EvaluationDrawer = defineAsyncComponent(() => import("../components/dashboard/EvaluationDrawer.vue"))
const JobTable = defineAsyncComponent(() => import("../components/dashboard/JobTable.vue"))

const router = useRouter()

type Job = {
  id: number
  name: string
  department: string | null
  status: string
  jd_content?: string
  updated_at: string
}

type RequirementItem = {
  id: number
  dimension_code: string
  name: string
  description: string | null
  requirement_type: string
  max_score: number
  is_gate: boolean
  acceptable_alternatives: string[] | null
  evidence_rule: string | null
}

type RequirementVersion = {
  id: number
  version_no: number
  summary: string | null
  status: string
  items: RequirementItem[]
}

type RequirementVersionMeta = {
  id: number
  version_no: number
  status: string
}

type CandidateRow = {
  application_id: number
  filename: string
  parse_status: string
  parse_task_id: number | null
  analysis_status: string
  analysis_progress: number
  evaluation_id: number | null
  score: number | null
  level: string | null
  gate_result: string | null
  decision: string | null
  uploaded_at: string
}

type Account = { id: number; email: string; name: string; role: string; status: string }

const stages = ["确认岗位模型", "上传简历", "AI事实提取", "规则评分", "人工决策"]
const loading = ref(true)
const initialized = ref(false)
const organizationId = ref<number | null>(Number(localStorage.getItem("organization_id")) || null)
const jobs = ref<Job[]>([])
const setupName = ref("")
const setupSubmitting = ref(false)
const currentUser = ref<Account | null>(JSON.parse(localStorage.getItem("current_user") || "null"))
const accountVisible = ref(false)
const accounts = ref<Account[]>([])
const accountSubmitting = ref(false)
const accountForm = reactive({ name: "", email: "", password: "" })

const createVisible = ref(false)
const createSubmitting = ref(false)
const editingJob = ref<Job | null>(null)

const analyzingJobId = ref<number | null>(null)
const requirementVisible = ref(false)
const requirementLoading = ref(false)
const publishing = ref(false)
const selectedJob = ref<Job | null>(null)
const requirement = ref<RequirementVersion | null>(null)
const versionList = ref<RequirementVersionMeta[]>([])
const savingScores = ref(false)

const uploadVisible = ref(false)
const uploadJob = ref<Job | null>(null)
const selectedFiles = ref<File[]>([])
const uploading = ref(false)
const uploadResults = ref<
  {
    filename: string
    status: string
    taskId: number
    progress: number
    duplicate: boolean
    matchRule: string
    message: string
  }[]
>([])
const retryingTaskId = ref<number | null>(null)

const candidatesVisible = ref(false)
const candidatesLoading = ref(false)
const candidatesJob = ref<Job | null>(null)
const candidates = ref<CandidateRow[]>([])
const selectedCandidates = ref<CandidateRow[]>([])
const batchAnalyzing = ref(false)
const gateFilter = ref("")
const retryingParseId = ref<number | null>(null)
let candidatePollTimer: number | null = null

const resultVisible = ref(false)
const resultLoading = ref(false)
const evaluationResult = ref<any>(null)
const decisionSubmitting = ref(false)
const decisionComment = ref("")

const scoreTotal = computed(() =>
  requirement.value?.items.reduce((total, item) => total + Number(item.max_score || 0), 0) || 0,
)
const scoresValid = computed(() => Math.abs(scoreTotal.value - 100) < 0.001)
const uploadReady = computed(() => selectedFiles.value.length > 0)
const form = reactive({ name: "", department: "", jd_content: "" })

const filteredCandidates = computed(() => {
  if (!gateFilter.value) return candidates.value
  return candidates.value.filter((item) => (item.gate_result || "") === gateFilter.value)
})

const reevaluateCount = computed(
  () => selectedCandidates.value.filter((item) => item.evaluation_id !== null).length,
)

const LEVEL_TEXT: Record<string, string> = {
  STRONGLY_RECOMMENDED: "强烈推荐",
  RECOMMENDED: "推荐",
  REVIEW: "待复核",
  LOW_MATCH: "低匹配",
}
const GATE_TEXT: Record<string, string> = {
  PASSED: "门槛通过",
  REVIEW_REQUIRED: "需人工复核",
  NOT_MET: "门槛未达",
}
const DECISION_TEXT: Record<string, string> = {
  ADVANCE: "进入面试",
  REJECT: "不通过",
  HOLD: "待定",
}
const ANALYSIS_STATUS_TEXT: Record<string, string> = {
  PENDING: "排队中",
  PROCESSING: "分析中",
  COMPLETED: "已完成",
  FAILED: "分析失败",
  NOT_ANALYZED: "未分析",
}

function levelText(v: string | null) {
  return v ? LEVEL_TEXT[v] || v : "--"
}
function gateText(v: string | null) {
  return v ? GATE_TEXT[v] || v : "--"
}
function decisionText(v: string | null) {
  return v ? DECISION_TEXT[v] || v : "--"
}
function analysisStatusText(v: string) {
  return ANALYSIS_STATUS_TEXT[v] || v
}
function gateTagType(v: string | null) {
  if (v === "PASSED") return "success"
  if (v === "NOT_MET") return "danger"
  if (v === "REVIEW_REQUIRED") return "warning"
  return "info"
}
function decisionTagType(v: string | null) {
  if (v === "ADVANCE") return "success"
  if (v === "REJECT") return "danger"
  return "warning"
}

async function logout() {
  localStorage.removeItem("access_token")
  localStorage.removeItem("current_user")
  localStorage.removeItem("organization_id")
  await router.replace("/login")
}

async function load() {
  loading.value = true
  try {
    const { data: setup } = await api.get("/setup/status")
    initialized.value = setup.initialized
    if (initialized.value && organizationId.value) {
      const { data } = await api.get("/jobs", { params: { organization_id: organizationId.value } })
      jobs.value = data
    }
  } catch {
    ElMessage.error("无法连接后端服务")
  } finally {
    loading.value = false
  }
}

async function bootstrap() {
  setupSubmitting.value = true
  try {
    const { data } = await api.post("/setup/bootstrap", { organization_name: setupName.value })
    organizationId.value = data.organization_id
    localStorage.setItem("organization_id", String(data.organization_id))
    initialized.value = true
    ElMessage.success("系统初始化完成")
    await load()
  } catch {
    ElMessage.error("初始化失败：后端服务不可用或数据库连接异常")
  } finally {
    setupSubmitting.value = false
  }
}

async function openAccounts() {
  accountVisible.value = true
  const { data } = await api.get("/auth/users")
  accounts.value = data
}

async function createAccount() {
  accountSubmitting.value = true
  try {
    await api.post("/auth/users", accountForm)
    Object.assign(accountForm, { name: "", email: "", password: "" })
    await openAccounts()
    ElMessage.success("普通用户已创建")
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "创建账户失败")
  } finally {
    accountSubmitting.value = false
  }
}

function openCreate() {
  editingJob.value = null
  Object.assign(form, { name: "", department: "", jd_content: "" })
  createVisible.value = true
}

function openEdit(job: Job) {
  editingJob.value = job
  Object.assign(form, {
    name: job.name,
    department: job.department || "",
    jd_content: job.jd_content || "",
  })
  createVisible.value = true
}

async function saveJob() {
  if (!organizationId.value) return
  createSubmitting.value = true
  try {
    if (editingJob.value) {
      await api.patch(`/jobs/${editingJob.value.id}`, { ...form })
      ElMessage.success("岗位已更新")
    } else {
      await api.post("/jobs", { organization_id: organizationId.value, ...form })
      ElMessage.success("岗位已创建")
    }
    createVisible.value = false
    Object.assign(form, { name: "", department: "", jd_content: "" })
    editingJob.value = null
    await load()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "保存失败，请检查后端服务")
  } finally {
    createSubmitting.value = false
  }
}

async function deleteJob(job: Job) {
  try {
    await ElMessageBox.confirm(
      `将永久删除岗位「${job.name}」及其能力模型、申请、评估与专属简历文件。被其他岗位使用的候选人和简历会保留。确定删除吗？`,
      "删除岗位",
      { confirmButtonText: "永久删除", cancelButtonText: "取消", type: "warning" },
    )
  } catch {
    return
  }
  try {
    await api.delete(`/jobs/${job.id}`)
    ElMessage.success("岗位已删除")
    await load()
  } catch {
    ElMessage.error("删除失败")
  }
}

async function analyzeJob(job: Job) {
  analyzingJobId.value = job.id
  try {
    const { data } = await api.post(`/jobs/${job.id}/analyze-jd`, undefined, { timeout: 120000 })
    ElMessage.success("JD分析完成，能力模型草稿已生成")
    await load()
    const jobAfter = jobs.value.find((item) => item.id === job.id) || job
    await openRequirement(jobAfter, data.id)
  } catch {
    ElMessage.error("JD分析失败，请查看后端日志")
  } finally {
    analyzingJobId.value = null
  }
}

async function openRequirement(job: Job, versionId?: number) {
  selectedJob.value = job
  requirementVisible.value = true
  requirementLoading.value = true
  try {
    const { data: versions } = await api.get(`/jobs/${job.id}/requirement-versions`)
    versionList.value = versions
    const id = versionId || versions[0]?.id
    if (!id) throw new Error("能力模型不存在")
    const { data } = await api.get(`/jobs/${job.id}/requirement-versions/${id}`)
    requirement.value = data
  } catch {
    ElMessage.error("能力模型加载失败")
    requirementVisible.value = false
  } finally {
    requirementLoading.value = false
  }
}

async function switchRequirementVersion(versionId: number) {
  if (!selectedJob.value) return
  requirementLoading.value = true
  try {
    const { data } = await api.get(
      `/jobs/${selectedJob.value.id}/requirement-versions/${versionId}`,
    )
    requirement.value = data
  } catch {
    ElMessage.error("版本加载失败")
  } finally {
    requirementLoading.value = false
  }
}

async function publishRequirement() {
  if (!selectedJob.value || !requirement.value) return
  publishing.value = true
  try {
    await api.patch(
      `/jobs/${selectedJob.value.id}/requirement-versions/${requirement.value.id}/scores`,
      {
        items: requirement.value.items.map((item) => ({
          item_id: item.id,
          max_score: Number(item.max_score),
        })),
      },
    )
    await api.post(
      `/jobs/${selectedJob.value.id}/requirement-versions/${requirement.value.id}/publish`,
    )
    requirement.value.status = "PUBLISHED"
    ElMessage.success("能力模型已发布，可以开始上传简历")
    await load()
  } catch {
    ElMessage.error("发布失败，请检查后端服务")
  } finally {
    publishing.value = false
  }
}

async function saveScores() {
  if (!selectedJob.value || !requirement.value || !scoresValid.value) return
  savingScores.value = true
  try {
    const { data } = await api.patch(
      `/jobs/${selectedJob.value.id}/requirement-versions/${requirement.value.id}/scores`,
      {
        items: requirement.value.items.map((item) => ({
          item_id: item.id,
          max_score: Number(item.max_score),
        })),
      },
    )
    requirement.value = data
    ElMessage.success("评分权重已保存")
  } catch {
    ElMessage.error("保存失败，请确认总分为100")
  } finally {
    savingScores.value = false
  }
}

function openUpload(job: Job) {
  uploadJob.value = job
  selectedFiles.value = []
  uploadResults.value = []
  uploadVisible.value = true
}

function selectResumeFiles(event: Event) {
  const input = event.target as HTMLInputElement
  selectedFiles.value = Array.from(input.files || [])
}

function duplicateMessage(matchRule: string) {
  if (matchRule === "phone") return "电话重复，已复用已有简历"
  if (matchRule === "email") return "未识别电话且邮箱重复，已复用已有简历"
  return "已复用已有简历"
}

async function uploadResumes() {
  if (!uploadJob.value || !selectedFiles.value.length) return
  uploading.value = true
  uploadResults.value = []
  for (const file of selectedFiles.value) {
    const formData = new FormData()
    formData.append("file", file)
    try {
      const { data } = await api.post(`/jobs/${uploadJob.value.id}/resumes`, formData, {
        timeout: 60000,
      })
      uploadResults.value.push({
        filename: file.name,
        status: data.status,
        taskId: data.task_id,
        progress: 0,
        duplicate: Boolean(data.duplicate),
        matchRule: data.match_rule,
        message: data.duplicate ? duplicateMessage(data.match_rule) : "已接收，等待解析",
      })
    } catch (error: any) {
      const detail = error?.response?.data?.detail
      const message = Array.isArray(detail)
        ? detail.map((item) => item.msg || item.type).join("；")
        : detail || "上传失败"
      uploadResults.value.push({
        filename: file.name,
        status: "UPLOAD_FAILED",
        taskId: 0,
        progress: 0,
        duplicate: false,
        matchRule: "",
        message,
      })
    }
  }
  uploading.value = false
  const success = uploadResults.value.filter((item) => item.status !== "UPLOAD_FAILED").length
  const duplicates = uploadResults.value.filter((item) => item.duplicate).length
  ElMessage.success(`已处理 ${success} 份简历${duplicates ? `，其中 ${duplicates} 份为重复复用` : ""}`)
  if (success) void pollUploadTasks()
}

async function pollUploadTasks() {
  const unfinished = uploadResults.value.filter(
    (item) => item.taskId && !["COMPLETED", "FAILED", "UPLOAD_FAILED"].includes(item.status),
  )
  if (!unfinished.length) return
  await Promise.all(
    unfinished.map(async (item) => {
      try {
        const { data } = await api.get(`/tasks/${item.taskId}`)
        item.status = data.status
        item.progress = data.progress
      } catch {
        // 下一轮继续查询，避免瞬时网络错误覆盖真实任务状态。
      }
    }),
  )
  if (
    uploadResults.value.some(
      (item) => item.taskId && !["COMPLETED", "FAILED", "UPLOAD_FAILED"].includes(item.status),
    )
  ) {
    window.setTimeout(pollUploadTasks, 2000)
  }
}

async function retryUploadTask(item: { taskId: number }) {
  retryingTaskId.value = item.taskId
  try {
    await api.post(`/tasks/${item.taskId}/retry`)
    ElMessage.success("已重新排队解析")
    const target = uploadResults.value.find((entry) => entry.taskId === item.taskId)
    if (target) {
      target.status = "PENDING"
      target.progress = 0
    }
    void pollUploadTasks()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "重试失败")
  } finally {
    retryingTaskId.value = null
  }
}

async function openCandidates(job: Job) {
  candidatesJob.value = job
  candidatesVisible.value = true
  selectedCandidates.value = []
  gateFilter.value = ""
  await loadCandidates()
}

async function loadCandidates() {
  if (!candidatesJob.value) return
  candidatesLoading.value = true
  try {
    const { data } = await api.get(`/jobs/${candidatesJob.value.id}/candidates`)
    candidates.value = data
    const running = candidates.value.some((item) => ["PENDING", "PROCESSING"].includes(item.analysis_status))
    if (running) {
      if (candidatePollTimer) window.clearTimeout(candidatePollTimer)
      candidatePollTimer = window.setTimeout(loadCandidates, 3000)
    }
  } catch {
    ElMessage.error("候选人列表加载失败")
  } finally {
    candidatesLoading.value = false
  }
}

function selectCandidates(rows: CandidateRow[]) {
  selectedCandidates.value = rows
}

function candidateSelectable(row: CandidateRow) {
  return row.parse_status === "COMPLETED" && !["PENDING", "PROCESSING"].includes(row.analysis_status)
}

async function submitBatchAnalyze(confirm: boolean) {
  if (!candidatesJob.value || !selectedCandidates.value.length) return
  batchAnalyzing.value = true
  try {
    const { data } = await api.post(`/jobs/${candidatesJob.value.id}/evaluations/batch`, {
      application_ids: selectedCandidates.value.map((item) => item.application_id),
      confirm_reevaluate: confirm,
    })
    ElMessage.success(`已提交 ${data.created.length} 份简历进行分析`)
    if (data.skipped.length) {
      ElMessage.warning(`${data.skipped.length} 份被跳过：${data.skipped[0].reason}`)
    }
    await loadCandidates()
  } catch {
    ElMessage.error("批量分析任务提交失败")
  } finally {
    batchAnalyzing.value = false
  }
}

async function batchAnalyzeCandidates() {
  if (!selectedCandidates.value.length) return
  if (reevaluateCount.value > 0) {
    try {
      await ElMessageBox.confirm(
        `选中有 ${reevaluateCount.value} 份简历已有评估结果，重新分析将生成新报告（历史结果保留）。确定继续吗？`,
        "确认重新分析",
        { confirmButtonText: "重新分析", cancelButtonText: "取消", type: "warning" },
      )
    } catch {
      return
    }
    await submitBatchAnalyze(true)
  } else {
    await submitBatchAnalyze(false)
  }
}

async function retryParse(row: CandidateRow) {
  if (!row.parse_task_id) return
  retryingParseId.value = row.application_id
  try {
    await api.post(`/tasks/${row.parse_task_id}/retry`)
    ElMessage.success("已重新排队解析")
    await loadCandidates()
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "重试失败")
  } finally {
    retryingParseId.value = null
  }
}

async function openEvaluation(evaluationId: number) {
  resultVisible.value = true
  resultLoading.value = true
  evaluationResult.value = null
  decisionComment.value = ""
  try {
    const { data } = await api.get(`/evaluations/${evaluationId}`)
    evaluationResult.value = data
  } catch {
    ElMessage.error("评估结果加载失败")
    resultVisible.value = false
  } finally {
    resultLoading.value = false
  }
}

async function submitDecision(decision: string) {
  if (!evaluationResult.value) return
  decisionSubmitting.value = true
  try {
    const { data } = await api.post(`/evaluations/${evaluationResult.value.id}/human-decision`, {
      decision,
      reason_code: "MANUAL",
      comment: decisionComment.value || null,
    })
    evaluationResult.value.human_decision = data
    const row = candidates.value.find(
      (item) => item.evaluation_id === evaluationResult.value.id,
    )
    if (row) row.decision = data.decision
    ElMessage.success(`已记录：${decisionText(data.decision)}`)
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "决策提交失败")
  } finally {
    decisionSubmitting.value = false
  }
}

onMounted(() => {
  if (!localStorage.getItem("access_token")) {
    void router.replace("/login")
    return
  }
  void load()
})
</script>

<template>
  <main class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">AI RECRUITING COPILOT</p>
        <h1>让每一次简历判断都有证据可循</h1>
      </div>
      <div class="hero-actions">
        <el-button v-if="currentUser?.role === 'ADMIN'" text size="small" @click="openAccounts">账户管理</el-button>
        <el-tag v-if="currentUser" effect="plain">{{ currentUser.name }} · {{ currentUser.role === 'ADMIN' ? '管理员' : '普通用户' }}</el-tag>
        <el-button text size="small" @click="logout">退出登录</el-button>
        <el-button v-if="initialized" type="primary" size="large" @click="openCreate">
          创建岗位
        </el-button>
      </div>
    </header>
    <section v-loading="loading" class="panel">
      <template v-if="!initialized">
        <div class="setup">
          <div>
            <p class="eyebrow">首次设置</p>
            <h2>初始化你的招聘空间</h2>
            <p class="muted">创建组织后即可添加岗位。这里不会创建默认候选人或演示数据。</p>
          </div>
          <el-input v-model="setupName" size="large" placeholder="请输入公司或团队名称" />
          <el-button
            type="primary"
            size="large"
            :loading="setupSubmitting"
            :disabled="setupName.trim().length < 2"
            @click="bootstrap"
          >
            完成初始化
          </el-button>
        </div>
      </template>
      <template v-else>
      <div class="panel-heading">
        <div>
          <p class="eyebrow">岗位中心</p>
          <h2>{{ jobs.length ? `${jobs.length} 个招聘岗位` : "从第一个岗位开始" }}</h2>
        </div>
        <el-tag effect="plain">数据库已连接</el-tag>
      </div>
      <div v-if="!jobs.length" class="stages">
        <div v-for="(stage, index) in stages" :key="stage" class="stage">
          <span>{{ String(index + 1).padStart(2, "0") }}</span>
          <strong>{{ stage }}</strong>
        </div>
      </div>
      <JobTable v-else :jobs="jobs" :analyzing-job-id="analyzingJobId" @upload="openUpload" @candidates="openCandidates" @requirement="openRequirement" @analyze="analyzeJob" @edit="openEdit" @delete="deleteJob" />
      </template>
    </section>

    <el-dialog v-model="createVisible" :title="editingJob ? '编辑岗位' : '创建招聘岗位'" width="min(640px, 92vw)">
      <el-form label-position="top">
        <el-form-item label="岗位名称"><el-input v-model="form.name" /></el-form-item>
        <el-form-item label="所属部门"><el-input v-model="form.department" /></el-form-item>
        <el-form-item label="岗位JD">
          <el-input v-model="form.jd_content" type="textarea" :rows="10" />
        </el-form-item>
      </el-form>
      <template #footer>
        <el-button @click="createVisible = false">取消</el-button>
        <el-button
          type="primary"
          :loading="createSubmitting"
          :disabled="!form.name.trim() || form.jd_content.trim().length < 10"
          @click="saveJob"
        >
          {{ editingJob ? "保存修改" : "创建岗位" }}
        </el-button>
      </template>
    </el-dialog>

    <el-dialog v-model="accountVisible" title="账户管理" width="min(620px, 92vw)">
      <el-form label-position="top" @submit.prevent="createAccount">
        <el-form-item label="姓名"><el-input v-model="accountForm.name" /></el-form-item>
        <el-form-item label="邮箱"><el-input v-model="accountForm.email" /></el-form-item>
        <el-form-item label="初始密码"><el-input v-model="accountForm.password" type="password" show-password /></el-form-item>
        <el-button type="primary" native-type="submit" :loading="accountSubmitting" :disabled="!accountForm.name || !accountForm.email || accountForm.password.length < 6">创建普通用户</el-button>
      </el-form>
      <el-table :data="accounts" style="margin-top: 20px"><el-table-column prop="name" label="姓名" /><el-table-column prop="email" label="邮箱" /><el-table-column label="角色"><template #default="{ row }">{{ row.role === 'ADMIN' ? '管理员' : '普通用户' }}</template></el-table-column></el-table>
    </el-dialog>

    <el-drawer v-model="requirementVisible" title="能力模型确认" size="min(760px, 94vw)">
      <div v-loading="requirementLoading" class="requirement-panel">
        <template v-if="requirement">
          <div class="requirement-head">
            <div>
              <p class="eyebrow">{{ selectedJob?.name }} · V{{ requirement.version_no }}</p>
              <h2>六维评分规则</h2>
            </div>
            <el-tag :type="requirement.status === 'PUBLISHED' ? 'success' : 'warning'">
              {{ requirement.status === "PUBLISHED" ? "已发布" : "待确认" }}
            </el-tag>
          </div>
          <div v-if="versionList.length > 1" class="version-switch">
            <span class="muted">历史版本：</span>
            <el-button
              v-for="v in versionList"
              :key="v.id"
              size="small"
              :type="v.id === requirement.id ? 'primary' : 'default'"
              round
              @click="switchRequirementVersion(v.id)"
            >
              V{{ v.version_no }}{{ v.status === "PUBLISHED" ? "·已发布" : "" }}
            </el-button>
          </div>
          <p class="summary">{{ requirement.summary }}</p>
          <div class="dimension-list">
            <article v-for="item in requirement.items" :key="item.id" class="dimension-card">
              <div class="dimension-title">
                <div>
                  <strong>{{ item.name }}</strong>
                  <el-tag v-if="item.is_gate" size="small" type="danger" effect="plain">硬门槛</el-tag>
                </div>
                <el-input-number
                  v-if="requirement.status !== 'PUBLISHED'"
                  v-model="item.max_score"
                  :min="0"
                  :max="100"
                  :step="1"
                  :precision="1"
                  controls-position="right"
                  aria-label="维度分数"
                />
                <span v-else>{{ item.max_score }} 分</span>
              </div>
              <p>{{ item.description }}</p>
              <small>证据要求：{{ item.evidence_rule || "简历直接证据" }}</small>
              <small v-if="item.acceptable_alternatives?.length">
                可替代能力：{{ item.acceptable_alternatives.join("、") }}
              </small>
            </article>
          </div>
          <div class="drawer-actions">
            <div v-if="requirement.status !== 'PUBLISHED'" class="score-total" :class="{ invalid: !scoresValid }">
              总分 <strong>{{ scoreTotal }}</strong> / 100
            </div>
            <div v-if="requirement.status !== 'PUBLISHED'" class="action-buttons">
              <el-button :loading="savingScores" :disabled="!scoresValid" @click="saveScores">
                保存调整
              </el-button>
              <el-button
                type="primary"
                size="large"
                :loading="publishing"
                :disabled="!scoresValid"
                @click="publishRequirement"
              >
                确认并发布
              </el-button>
            </div>
          </div>
        </template>
      </div>
    </el-drawer>

    <el-dialog v-model="uploadVisible" title="上传PDF简历" width="min(620px, 92vw)">
      <div class="upload-panel">
        <p class="muted">岗位：{{ uploadJob?.name }}。系统会自动从PDF识别姓名、电话和邮箱来校验重复。</p>
        <label class="file-picker">
          <input type="file" accept="application/pdf,.pdf" multiple @change="selectResumeFiles" />
          <span>{{ selectedFiles.length ? `已选择 ${selectedFiles.length} 份简历` : "选择PDF简历" }}</span>
        </label>
        <ul v-if="selectedFiles.length" class="file-list">
          <li v-for="file in selectedFiles" :key="`${file.name}-${file.size}`">
            <span>{{ file.name }}</span><small>{{ (file.size / 1024 / 1024).toFixed(2) }} MB</small>
          </li>
        </ul>
        <ul v-if="uploadResults.length" class="result-list">
          <li v-for="result in uploadResults" :key="result.filename">
            <div class="upload-result-meta">
              <span>{{ result.filename }}</span>
              <small v-if="result.duplicate">重复命中：{{ result.matchRule }}</small>
            </div>
            <div class="upload-result-side">
              <el-tag
                :type="
                  result.status === 'COMPLETED'
                    ? 'success'
                    : ['FAILED', 'UPLOAD_FAILED'].includes(result.status)
                      ? 'danger'
                      : 'warning'
                "
              >
                {{
                  result.status === "COMPLETED"
                    ? "解析完成"
                    : result.status === "UPLOAD_FAILED"
                      ? `上传失败：${result.message}`
                      : result.status === "FAILED"
                        ? "解析失败"
                        : `解析中 ${result.progress}%`
                }}
              </el-tag>
              <el-button
                v-if="result.status === 'FAILED' && result.taskId"
                link
                type="primary"
                size="small"
                :loading="retryingTaskId === result.taskId"
                @click="retryUploadTask(result)"
              >
                重试
              </el-button>
            </div>
          </li>
        </ul>
      </div>
      <template #footer>
        <el-button @click="uploadVisible = false">关闭</el-button>
        <el-button
          type="primary"
          :loading="uploading"
          :disabled="!uploadReady"
          @click="uploadResumes"
        >
          开始上传
        </el-button>
      </template>
    </el-dialog>

    <el-drawer v-model="candidatesVisible" title="候选人批量分析" size="min(1180px, 96vw)">
      <div class="candidate-toolbar">
        <div>
          <p class="eyebrow">{{ candidatesJob?.name }}</p>
          <h2>已上传简历 {{ candidates.length }} 份</h2>
        </div>
        <div class="candidate-filters">
          <el-select v-model="gateFilter" placeholder="门槛结果" clearable style="width: 150px">
            <el-option label="门槛通过" value="PASSED" />
            <el-option label="需人工复核" value="REVIEW_REQUIRED" />
            <el-option label="门槛未达" value="NOT_MET" />
          </el-select>
          <el-button
            type="primary"
            size="large"
            :loading="batchAnalyzing"
            :disabled="!selectedCandidates.length"
            @click="batchAnalyzeCandidates"
          >
            批量分析 {{ selectedCandidates.length || "" }}
          </el-button>
        </div>
      </div>
      <el-alert
        title="简历只需上传一次。勾选已有简历后可反复按当前岗位规则重新分析，历史结果会保留。"
        type="info"
        :closable="false"
        show-icon
      />
      <el-table
        v-loading="candidatesLoading"
        :data="filteredCandidates"
        row-key="application_id"
        class="candidate-table"
        @selection-change="selectCandidates"
      >
        <el-table-column type="selection" width="48" :selectable="candidateSelectable" />
        <el-table-column prop="filename" label="简历" min-width="200" show-overflow-tooltip />
        <el-table-column label="解析" width="150">
          <template #default="{ row }">
            <el-tag v-if="row.parse_status === 'COMPLETED'" type="success" effect="plain">已解析</el-tag>
            <div v-else class="parse-failed">
              <el-tag type="danger" effect="plain">{{ row.parse_status }}</el-tag>
              <el-button
                v-if="row.parse_task_id"
                link
                type="primary"
                size="small"
                :loading="retryingParseId === row.application_id"
                @click="retryParse(row)"
              >
                重试
              </el-button>
            </div>
          </template>
        </el-table-column>
        <el-table-column label="AI分析" width="130">
          <template #default="{ row }">
            <span v-if="['PENDING', 'PROCESSING'].includes(row.analysis_status)">
              分析中 {{ row.analysis_progress }}%
            </span>
            <span v-else>{{ analysisStatusText(row.analysis_status) }}</span>
          </template>
        </el-table-column>
        <el-table-column label="得分" width="100" sortable :sort-method="(a: CandidateRow, b: CandidateRow) => (a.score ?? -1) - (b.score ?? -1)">
          <template #default="{ row }">
            <strong v-if="row.score !== null" class="candidate-score">{{ row.score }}</strong>
            <span v-else>--</span>
          </template>
        </el-table-column>
        <el-table-column label="推荐等级" min-width="110">
          <template #default="{ row }">{{ levelText(row.level) }}</template>
        </el-table-column>
        <el-table-column label="门槛结果" min-width="120">
          <template #default="{ row }">
            <el-tag v-if="row.gate_result" :type="gateTagType(row.gate_result)" effect="plain">
              {{ gateText(row.gate_result) }}
            </el-tag>
            <span v-else>--</span>
          </template>
        </el-table-column>
        <el-table-column label="人工决策" min-width="110">
          <template #default="{ row }">
            <el-tag v-if="row.decision" :type="decisionTagType(row.decision)">
              {{ decisionText(row.decision) }}
            </el-tag>
            <span v-else>--</span>
          </template>
        </el-table-column>
        <el-table-column label="结果" width="90" fixed="right">
          <template #default="{ row }">
            <el-button v-if="row.evaluation_id" link type="primary" @click="openEvaluation(row.evaluation_id)">
              查看
            </el-button>
          </template>
        </el-table-column>
      </el-table>
    </el-drawer>

    <EvaluationDrawer
      v-model:visible="resultVisible"
      v-model:comment="decisionComment"
      :loading="resultLoading"
      :result="evaluationResult"
      :submitting="decisionSubmitting"
      @decide="submitDecision"
    />
  </main>
</template>
