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
  <main class="shell"><section class="panel setup"><div><p class="eyebrow">AI RECRUITING COPILOT</p><h2>{{ needsAdminSetup ? "创建管理员账号" : "登录招聘工作台" }}</h2></div><el-form v-if="needsAdminSetup" @submit.prevent="createAdmin"><el-form-item label="姓名"><el-input v-model="admin.name" /></el-form-item><el-form-item label="邮箱"><el-input v-model="admin.email" /></el-form-item><el-form-item label="初始密码"><el-input v-model="admin.password" type="password" show-password /></el-form-item><el-button type="primary" native-type="submit" :loading="submitting" :disabled="!admin.name || !admin.email || admin.password.length < 6">创建管理员</el-button></el-form><el-form v-else @submit.prevent="login"><el-form-item label="邮箱"><el-input v-model="form.email" /></el-form-item><el-form-item label="密码"><el-input v-model="form.password" type="password" show-password /></el-form-item><el-button type="primary" native-type="submit" :loading="submitting" :disabled="!form.email || !form.password">登录</el-button></el-form></section></main>
</template>
