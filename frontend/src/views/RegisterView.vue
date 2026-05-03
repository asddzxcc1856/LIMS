<template>
  <div class="auth-stage">
    <div class="auth-bg-blob auth-bg-blob--purple"></div>
    <div class="auth-bg-blob auth-bg-blob--blue"></div>

    <a-card class="auth-card" :bordered="false">
      <div class="auth-brand">
        <UserAddOutlined class="brand-icon" />
        <h1 class="brand-title">註冊新帳號</h1>
        <p class="brand-subtitle">加入 LIMS,開始使用實驗室排程系統</p>
      </div>

      <a-result
        v-if="success"
        status="success"
        title="註冊成功!"
        sub-title="您現在可以登入使用系統"
      >
        <template #extra>
          <router-link to="/login">
            <a-button type="primary" size="large">前往登入</a-button>
          </router-link>
        </template>
      </a-result>

      <a-form
        v-else
        :model="form"
        layout="vertical"
        @finish="handleRegister"
      >
        <a-form-item
          label="Username"
          name="username"
          :rules="[
            { required: true, message: '請輸入帳號' },
            { min: 3, message: '帳號至少 3 字元' },
          ]"
        >
          <a-input v-model:value="form.username" placeholder="3 字元以上">
            <template #prefix><UserOutlined /></template>
          </a-input>
        </a-form-item>

        <a-form-item
          label="Email"
          name="email"
          :rules="[
            { required: true, message: '請輸入 Email' },
            { type: 'email', message: '需為合法 Email 格式' },
          ]"
        >
          <a-input v-model:value="form.email" placeholder="example@lims.local">
            <template #prefix><MailOutlined /></template>
          </a-input>
        </a-form-item>

        <a-form-item
          label="密碼"
          name="password"
          :rules="[
            { required: true, message: '請輸入密碼' },
            { min: 8, message: '密碼至少 8 字元' },
          ]"
        >
          <a-input-password v-model:value="form.password" placeholder="至少 8 字元">
            <template #prefix><LockOutlined /></template>
          </a-input-password>
        </a-form-item>

        <a-form-item
          label="姓名"
          name="first_name"
          :rules="[{ required: true, message: '請輸入姓名' }]"
        >
          <a-input v-model:value="form.first_name" placeholder="顯示名稱" />
        </a-form-item>

        <a-form-item label="角色" name="role">
          <a-select v-model:value="form.role" :options="roleOptions" />
        </a-form-item>

        <a-alert
          v-if="error"
          type="error"
          :message="error"
          show-icon
          banner
          style="margin-bottom: 16px"
        />

        <a-button
          type="primary"
          html-type="submit"
          :loading="loading"
          block
          size="large"
        >
          建立帳號
        </a-button>

        <div class="back-link">
          已有帳號?
          <router-link to="/login">回登入頁</router-link>
        </div>
      </a-form>
    </a-card>
  </div>
</template>

<script setup>
import { reactive, ref } from 'vue'
import {
  LockOutlined,
  MailOutlined,
  UserAddOutlined,
  UserOutlined,
} from '@ant-design/icons-vue'
import client from '../api/client'

const form = reactive({
  username: '',
  email: '',
  password: '',
  first_name: '',
  last_name: '',
  role: 'regular_employee',
})

const roleOptions = [
  { value: 'regular_employee', label: '一般員工 (送樣申請)' },
  { value: 'lab_manager', label: '實驗室經理' },
  { value: 'lab_member', label: '實驗室成員' },
]

const loading = ref(false)
const error = ref('')
const success = ref(false)

async function handleRegister() {
  error.value = ''
  loading.value = true
  try {
    await client.post('/users/register/', form)
    success.value = true
  } catch (e) {
    const data = e.response?.data
    if (typeof data === 'string') error.value = data
    else if (data?.detail) error.value = data.detail
    else if (data && typeof data === 'object') {
      const k = Object.keys(data)[0]
      error.value = `${k}: ${Array.isArray(data[k]) ? data[k].join(', ') : data[k]}`
    } else error.value = '註冊失敗'
  } finally {
    loading.value = false
  }
}
</script>

<style scoped>
.auth-stage {
  position: relative;
  min-height: 100vh;
  display: flex;
  align-items: center;
  justify-content: center;
  overflow: hidden;
  padding: 24px 0;
  background: linear-gradient(135deg, #eff6ff 0%, #ede9fe 100%);
}
.auth-bg-blob {
  position: absolute;
  width: 480px;
  height: 480px;
  border-radius: 50%;
  filter: blur(80px);
  opacity: 0.55;
  pointer-events: none;
}
.auth-bg-blob--purple {
  background: #a78bfa;
  top: -100px;
  left: -120px;
}
.auth-bg-blob--blue {
  background: #60a5fa;
  bottom: -120px;
  right: -120px;
}
.auth-card {
  position: relative;
  z-index: 1;
  width: 100%;
  max-width: 480px;
  border-radius: 16px;
  box-shadow: 0 20px 60px rgba(15, 23, 42, 0.12);
  background: rgba(255, 255, 255, 0.96);
  backdrop-filter: blur(8px);
}
.auth-brand {
  text-align: center;
  margin-bottom: 24px;
}
.brand-icon {
  font-size: 40px;
  color: #1890ff;
  margin-bottom: 8px;
}
.brand-title {
  font-size: 24px;
  font-weight: 700;
  margin: 0 0 4px;
  background: linear-gradient(135deg, #1890ff, #722ed1);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
  background-clip: text;
}
.brand-subtitle {
  margin: 0;
  font-size: 12px;
  color: rgba(0, 0, 0, 0.45);
}
.back-link {
  text-align: center;
  margin-top: 16px;
  font-size: 13px;
  color: rgba(0, 0, 0, 0.45);
}
</style>
