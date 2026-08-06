import { createPinia } from "pinia"
import { createApp } from "vue"
import {
  ElAlert,
  ElButton,
  ElDialog,
  ElDrawer,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElLoading,
  ElOption,
  ElPagination,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTooltip,
} from "element-plus"
import "element-plus/dist/index.css"

import App from "./App.vue"
import router from "./router"
import "./styles.css"

const app = createApp(App)
app.use(createPinia()).use(router)
for (const component of [
  ElAlert,
  ElButton,
  ElDialog,
  ElDrawer,
  ElEmpty,
  ElForm,
  ElFormItem,
  ElInput,
  ElInputNumber,
  ElLoading,
  ElOption,
  ElPagination,
  ElSelect,
  ElTable,
  ElTableColumn,
  ElTag,
  ElTooltip,
]) {
  app.use(component)
}
app.mount("#app")
