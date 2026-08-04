import { createRouter, createWebHistory } from "vue-router"

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: () => import("../views/DashboardView.vue") },
    { path: "/login", name: "login", component: () => import("../views/LoginView.vue") },
  ],
})
