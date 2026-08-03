import { createRouter, createWebHistory } from "vue-router"

import DashboardView from "../views/DashboardView.vue"
import LoginView from "../views/LoginView.vue"

export default createRouter({
  history: createWebHistory(),
  routes: [
    { path: "/", name: "dashboard", component: DashboardView },
    { path: "/login", name: "login", component: LoginView },
  ],
})
