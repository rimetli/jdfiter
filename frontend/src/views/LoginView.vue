<script setup lang="ts">
import { onMounted, reactive, ref } from "vue"
import { ElMessage } from "element-plus"
import { useRouter } from "vue-router"

import { api } from "../api/client"

const router = useRouter()
const submitting = ref(false)
const needsAdminSetup = ref(false)
const form = reactive({ email: "", password: "" })
const admin = reactive({ email: "", name: "", password: "" })

async function login() {
  submitting.value = true
  try {
    const { data } = await api.post("/auth/login", form)
    localStorage.setItem("access_token", data.access_token)
    localStorage.setItem("current_user", JSON.stringify(data.user))
    await router.replace("/")
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "登录失败")
  } finally {
    submitting.value = false
  }
}

async function createAdmin() {
  submitting.value = true
  try {
    await api.post("/setup/admin", admin)
    form.email = admin.email
    form.password = admin.password
    needsAdminSetup.value = false
    ElMessage.success("管理员账号已创建，请登录")
  } catch (error: any) {
    ElMessage.error(error?.response?.data?.detail || "创建管理员失败")
  } finally {
    submitting.value = false
  }
}

onMounted(async () => {
  const { data } = await api.get("/setup/status")
  needsAdminSetup.value = data.needs_admin_setup === true
})
</script>

<template>
  <main class="login-page">
    <section class="login-intro">
      <p class="eyebrow">AI RECRUITING COPILOT</p>
      <h1>让每一次筛选<br />都有证据可循</h1>
      <p class="login-subtitle">从岗位模型到候选人结论，AI 负责归纳和评分，人始终负责最终决策。</p>
      <ol class="flow-steps" aria-label="简历筛选流程">
        <li><span>01</span><div><strong>确认岗位模型</strong><small>输入 JD，人工调整能力项与评分权重</small></div></li>
        <li><span>02</span><div><strong>上传并解析简历</strong><small>自动识别 PDF、扫描件与重复候选人</small></div></li>
        <li><span>03</span><div><strong>批量分析与人工决策</strong><small>查看证据、风险和面试建议，再作最终结论</small></div></li>
      </ol>
    </section>
    <section class="login-card">
      <div class="login-card-head"><p class="eyebrow">{{ needsAdminSetup ? "首次设置" : "欢迎回来" }}</p><h2>{{ needsAdminSetup ? "创建管理员账号" : "登录招聘工作台" }}</h2><p class="muted">{{ needsAdminSetup ? "管理员可创建普通账户并统一查看招聘数据。" : "使用管理员创建的账户和密码登录。" }}</p></div>
      <el-form v-if="needsAdminSetup" class="login-form" @submit.prevent="createAdmin"><el-form-item label="姓名"><el-input v-model="admin.name" placeholder="请输入姓名" /></el-form-item><el-form-item label="邮箱"><el-input v-model="admin.email" placeholder="name@company.com" /></el-form-item><el-form-item label="初始密码"><el-input v-model="admin.password" type="password" show-password placeholder="至少 6 位" /></el-form-item><el-button type="primary" native-type="submit" :loading="submitting" :disabled="!admin.name || !admin.email || admin.password.length < 6">创建管理员账号</el-button></el-form>
      <el-form v-else class="login-form" @submit.prevent="login"><el-form-item label="邮箱"><el-input v-model="form.email" placeholder="name@company.com" /></el-form-item><el-form-item label="密码"><el-input v-model="form.password" type="password" show-password placeholder="请输入密码" /></el-form-item><el-button type="primary" native-type="submit" :loading="submitting" :disabled="!form.email || !form.password">登录工作台</el-button></el-form>
      <p class="login-note">系统仅提供招聘辅助建议，不自动做出录用或淘汰决定。</p>
    </section>
  </main>
</template>
