<script setup lang="ts">
const stages = ["确认岗位模型", "上传简历", "AI事实提取", "规则评分", "人工决策"]
</script>

<template>
  <main class="shell">
    <header class="hero">
      <div>
        <p class="eyebrow">AI RECRUITING COPILOT</p>
        <h1>让每一次简历判断<br />都有证据可循</h1>
        <p class="subtitle">基于岗位规则进行可解释评分，AI提供建议，决定始终由人完成。</p>
      </div>
      <el-button type="primary" size="large">创建第一个岗位</el-button>
    </header>

    <section class="panel">
      <div class="panel-heading">
        <div>
          <p class="eyebrow">工作流</p>
          <h2>从JD到面试建议</h2>
        </div>
        <el-tag effect="plain">本地工程已启动</el-tag>
      </div>
      <div class="stages">
        <div v-for="(stage, index) in stages" :key="stage" class="stage">
          <span>{{ String(index + 1).padStart(2, "0") }}</span>
          <strong>{{ stage }}</strong>
        </div>
      </div>
    </section>
  </main>
</template>

