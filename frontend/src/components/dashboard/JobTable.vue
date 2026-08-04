<script setup lang="ts">
defineProps<{ jobs: any[]; analyzingJobId: number | null }>()
const emit = defineEmits(["upload", "candidates", "requirement", "analyze", "edit", "delete"])
const statusText = (value: string) => ({ DRAFT: "草稿", REVIEW: "待确认", ACTIVE: "招聘中" } as Record<string, string>)[value] || value
</script>
<template>
  <el-table :data="jobs" class="jobs-table">
    <el-table-column prop="name" label="岗位" min-width="160" />
    <el-table-column prop="department" label="部门" min-width="120" />
    <el-table-column label="所属账号" min-width="120">
      <template #default="{ row }">{{ row.owner_name || "未知账号" }}</template>
    </el-table-column>
    <el-table-column label="状态" width="100"><template #default="{ row }"><el-tag :type="row.status === 'ACTIVE' ? 'success' : 'warning'" effect="plain">{{ statusText(row.status) }}</el-tag></template></el-table-column>
    <el-table-column label="操作" width="360" fixed="right"><template #default="{ row }"><el-button v-if="row.status === 'ACTIVE'" link type="primary" @click="emit('upload', row)">上传简历</el-button><el-button v-if="row.status === 'ACTIVE'" link type="success" @click="emit('candidates', row)">候选人</el-button><el-button v-if="row.status !== 'DRAFT'" link type="success" @click="emit('requirement', row)">能力模型</el-button><el-button v-if="row.status === 'DRAFT'" link type="primary" :loading="analyzingJobId === row.id" @click="emit('analyze', row)">AI分析JD</el-button><el-button link @click="emit('edit', row)">编辑</el-button><el-button link type="danger" @click="emit('delete', row)">删除</el-button></template></el-table-column>
  </el-table>
</template>
