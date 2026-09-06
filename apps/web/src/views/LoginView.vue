<script setup lang="ts">
/**
 * 登录页 v5.3 —— uiverse @JohnnyCSilva/bad-cheetah-74【精准复刻·最终版】（MIT，保留版权声明）
 * v5.3（2026-09-06 组长反馈）：Sign Up = **真实注册**（原有业务端点 /auth/register，注册即登录），
 * 不再是一键填演示账号；Forgot password = 忘记密码申请（演示环境无邮件/短信通道 → 落管理员工单
 * POST /auth/forgot，防枚举同响应）；第三方登录仍为占位提示。
 */
import { ref } from 'vue'
import { useRouter } from 'vue-router'

import IconUser from '~icons/tabler/user'
import { useAuthStore } from '@/stores/auth'
import '@/styles/mobile-soft.css'

type Mode = 'login' | 'register' | 'forgot'

const router = useRouter()
const auth = useAuthStore()

const mode = ref<Mode>('login')

/* ---- 登录 ---- */
const username = ref('')
const password = ref('')
/* ---- 注册 ---- */
const regUsername = ref('')
const regNickname = ref('')
const regPassword = ref('')
/* ---- 忘记密码 ---- */
const forgotUsername = ref('')
const forgotDone = ref(false)

const errorMsg = ref('')
const notice = ref('')
const loading = ref(false)
const success = ref(false)

function switchMode(m: Mode) {
  mode.value = m
  errorMsg.value = ''
  notice.value = ''
  forgotDone.value = false
  success.value = false
}

async function submit() {
  if (loading.value) return
  loading.value = true
  errorMsg.value = ''
  try {
    await auth.login(username.value.trim(), password.value)
    loading.value = false
    success.value = true
    setTimeout(() => {
      void router.push((router.currentRoute.value.query.redirect as string) ?? '/m/home')
    }, 200)
  } catch (e) {
    errorMsg.value = (e as Error).message
    loading.value = false
  }
}

/** 注册即登录（Java /auth/register；演示环境 nickname 必填、ageGroup 默认成年中级） */
async function register() {
  if (loading.value) return
  loading.value = true
  errorMsg.value = ''
  try {
    await auth.register({
      username: regUsername.value.trim(),
      password: regPassword.value,
      nickname: regNickname.value.trim(),
      ageGroup: 'adult',
    })
    loading.value = false
    success.value = true
    setTimeout(() => {
      void router.push((router.currentRoute.value.query.redirect as string) ?? '/m/home')
    }, 200)
  } catch (e) {
    errorMsg.value = (e as Error).message
    loading.value = false
  }
}

/** 忘记密码：提交申请 → 管理员工单（无邮件通道的演示口径） */
async function forgot() {
  if (loading.value) return
  const name = forgotUsername.value.trim()
  if (!name) return
  loading.value = true
  errorMsg.value = ''
  try {
    const message = await auth.forgotPassword(name)
    notice.value = message
    forgotDone.value = true
    loading.value = false
  } catch (e) {
    errorMsg.value = (e as Error).message
    loading.value = false
  }
}

function notReady(text: string) {
  notice.value = text
  setTimeout(() => {
    notice.value = ''
  }, 2400)
}
</script>

<template>
  <div class="s-login">
    <form class="form" @submit.prevent="mode === 'register' ? register() : submit()">
      <template v-if="mode === 'login'">
        <div class="inputForm">
          <IconUser aria-hidden="true" />
          <input
            id="vv-username"
            v-model="username"
            class="input"
            placeholder="Enter your Username"
            aria-label="Username"
            name="username"
            autocomplete="username"
          >
        </div>

        <div class="inputForm">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" viewBox="-64 0 512 512" height="20">
            <path
              d="m336 512h-288c-26.453125 0-48-21.523438-48-48v-224c0-26.476562 21.546875-48 48-48h288c26.453125 0 48 21.523438 48 48v224c0 26.476562-21.546875 48-48 48zm-288-288c-8.8125 0-16 7.167969-16 16v224c0 8.832031 7.1875 16 16 16h288c8.8125 0 16-7.167969 16-16v-224c0-8.832031-7.1875-16-16-16zm0 0"
            />
            <path
              d="m304 224c-8.832031 0-16-7.167969-16-16v-80c0-52.929688-43.070312-96-96-96s-96 43.070312-96 96v80c0 8.832031-7.167969 16-16 16s-16-7.167969-16-16v-80c0-70.59375 57.40625-128 128-128s128 57.40625 128 128v80c0 8.832031-7.167969 16-16 16zm0 0"
            />
          </svg>
          <input
            id="vv-password"
            v-model="password"
            class="input"
            placeholder="Enter your Password"
            aria-label="Password"
            type="password"
            name="password"
            autocomplete="current-password"
          >
        </div>

        <div class="flex-row">
          <div>
            <input id="remember" type="radio" name="remember">
            <label for="remember">Remember me </label>
          </div>
          <span class="span" role="button" tabindex="0" @click="switchMode('forgot')">Forgot password?</span>
        </div>
        <button class="button-submit" type="submit" :disabled="loading">
          {{ success ? 'Signed In' : loading ? 'Signing in…' : 'Sign In' }}
        </button>
        <p class="p">Don't have an account? <span class="span" role="button" tabindex="0" @click="switchMode('register')">Sign Up</span></p>
      </template>

      <template v-else-if="mode === 'register'">
        <p class="p line">Create your account</p>
        <div class="inputForm">
          <IconUser aria-hidden="true" />
          <input
            id="reg-username"
            v-model="regUsername"
            class="input"
            placeholder="Username"
            aria-label="注册用户名"
            name="reg-username"
            autocomplete="username"
          >
        </div>
        <div class="inputForm">
          <IconUser aria-hidden="true" />
          <input
            id="reg-nickname"
            v-model="regNickname"
            class="input"
            placeholder="Nickname"
            aria-label="昵称"
            name="reg-nickname"
            autocomplete="nickname"
          >
        </div>
        <div class="inputForm">
          <svg xmlns="http://www.w3.org/2000/svg" width="20" viewBox="-64 0 512 512" height="20">
            <path
              d="m336 512h-288c-26.453125 0-48-21.523438-48-48v-224c0-26.476562 21.546875-48 48-48h288c26.453125 0 48 21.523438 48 48v224c0 26.476562-21.546875 48-48 48zm-288-288c-8.8125 0-16 7.167969-16 16v224c0 8.832031 7.1875 16 16 16h288c8.8125 0 16-7.167969 16-16v-224c0-8.832031-7.1875-16-16-16zm0 0"
            />
            <path
              d="m304 224c-8.832031 0-16-7.167969-16-16v-80c0-52.929688-43.070312-96-96-96s-96 43.070312-96 96v80c0 8.832031-7.167969 16-16 16s-16-7.167969-16-16v-80c0-70.59375 57.40625-128 128-128s128 57.40625 128 128v80c0 8.832031-7.167969 16-16 16zm0 0"
            />
          </svg>
          <input
            id="reg-password"
            v-model="regPassword"
            class="input"
            placeholder="Password (min 8)"
            aria-label="注册密码"
            type="password"
            name="reg-password"
            autocomplete="new-password"
          >
        </div>
        <button class="button-submit" type="submit" :disabled="loading || !regUsername.trim() || !regNickname.trim() || !regPassword">
          {{ loading ? 'Creating…' : 'Sign Up' }}
        </button>
        <p class="p">Already have an account? <span class="span" role="button" tabindex="0" @click="switchMode('login')">Sign In</span></p>
      </template>

      <template v-else>
        <p class="p line">Reset your password</p>
        <p class="p note-text">Enter your username and we'll file a password reset request for the admin. （演示环境无邮件通道，管理员工单处理）</p>
        <div class="inputForm">
          <IconUser aria-hidden="true" />
          <input
            id="forgot-username"
            v-model="forgotUsername"
            class="input"
            placeholder="Your Username"
            aria-label="忘记密码用户名"
            name="forgot-username"
            autocomplete="username"
          >
        </div>
        <button class="button-submit" type="button" :disabled="loading || !forgotUsername.trim()" @click="forgot">
          {{ loading ? 'Submitting…' : 'Submit Request' }}
        </button>
        <p class="p"><span class="span" role="button" tabindex="0" @click="switchMode('login')">Back to Sign In</span></p>
      </template>

      <p class="p line">Or With</p>

      <div class="flex-row">
        <button class="btn google" type="button" @click="notReady('Third-party sign in coming soon')">
          <svg
            xml:space="preserve"
            style="enable-background:new 0 0 512 512"
            viewBox="0 0 512 512"
            y="0px"
            x="0px"
            xmlns:xlink="http://www.w3.org/1999/xlink"
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            version="1.1"
          >
            <path
              d="M113.47,309.408L95.648,375.94l-65.139,1.378C11.042,341.211,0,299.9,0,256	c0-42.451,10.324-82.483,28.624-117.732h0.014l57.992,10.632l25.404,57.644c-5.317,15.501-8.215,32.141-8.215,49.456	C103.821,274.792,107.225,292.797,113.47,309.408z"
              style="fill:#FBBB00"
            />
            <path
              d="M507.527,208.176C510.467,223.662,512,239.655,512,256c0,18.328-1.927,36.206-5.598,53.451	c-12.462,58.683-45.025,109.925-90.134,146.187l-0.014-0.014l-73.044-3.727l-10.338-64.535	c29.932-17.554,53.324-45.025,65.646-77.911h-136.89V208.176h138.887L507.527,208.176L507.527,208.176z"
              style="fill:#518EF8"
            />
            <path
              d="M416.253,455.624l0.014,0.014C372.396,490.901,316.666,512,256,512	c-97.491,0-182.252-54.491-225.491-134.681l82.961-67.91c21.619,57.698,77.278,98.771,142.53,98.771	c28.047,0,54.323-7.582,76.87-20.818L416.253,455.624z"
              style="fill:#28B446"
            />
            <path
              d="M419.404,58.936l-82.933,67.896c-23.335-14.586-50.919-23.012-80.471-23.012	c-66.729,0-123.429,42.957-143.965,102.724l-83.397-68.276h-0.014C71.23,56.123,157.06,0,256,0	C318.115,0,375.068,22.126,419.404,58.936z"
              style="fill:#F14336"
            />
          </svg>

          Google
        </button>
        <button class="btn apple" type="button" @click="notReady('Third-party sign in coming soon')">
          <svg
            xml:space="preserve"
            style="enable-background:new 0 0 22.773 22.773"
            viewBox="0 0 22.773 22.773"
            y="0px"
            x="0px"
            xmlns:xlink="http://www.w3.org/1999/xlink"
            xmlns="http://www.w3.org/2000/svg"
            width="20"
            height="20"
            version="1.1"
          >
            <g>
              <g>
                <path
                  d="M15.769,0c0.053,0,0.106,0,0.162,0c0.13,1.606-0.483,2.806-1.228,3.675c-0.731,0.863-1.732,1.7-3.351,1.573 c-0.108-1.583,0.506-2.694,1.25-3.561C13.292,0.879,14.557,0.16,15.769,0z"
                />
                <path
                  d="M20.67,16.716c0,0.016,0,0.03,0,0.045c-0.455,1.378-1.104,2.559-1.896,3.655c-0.723,0.995-1.609,2.334-3.191,2.334 c-1.367,0-2.275-0.879-3.676-0.903c-1.482-0.024-2.297,0.735-3.652,0.926c-0.155,0-0.31,0-0.462,0 c-0.995-0.144-1.798-0.932-2.383-1.642c-1.725-2.098-3.058-4.808-3.306-8.276c0-0.34,0-0.679,0-1.019 c0.105-2.482,1.311-4.5,2.914-5.478c0.846-0.52,2.009-0.963,3.304-0.765c0.555,0.086,1.122,0.276,1.619,0.464 c0.471,0.181,1.06,0.502,1.618,0.485c0.378-0.011,0.754-0.208,1.135-0.347c1.116-0.403,2.21-0.865,3.652-0.648 c1.733,0.262,2.963,1.032,3.723,2.22c-1.466,0.933-2.625,2.339-2.427,4.74C17.818,14.688,19.086,15.964,20.67,16.716z"
                />
              </g>
            </g>
          </svg>

          Apple
        </button>
      </div>
      <p v-if="notice" class="p notice">{{ notice }}</p>
      <p v-if="errorMsg" class="error-line" role="alert" aria-live="polite">{{ errorMsg }}</p>
    </form>
  </div>
</template>

<style scoped>
/* ============================================================
 * bad-cheetah-74 精准复刻样式（原样照搬 + 选中框线修正）
 * 版权与授权：© 2026 JohnnyCSilva (João Silva) · MIT（保留声明）
 * ============================================================ */
.s-login {
  min-height: 100dvh;
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
  background: #f0f0f0;
  width: 100%;
  box-sizing: border-box; /* 2026-09-06 防御：任何外层收窄/盒模型干扰下登录卡仍全宽居中 */
}

.form {
  display: flex;
  flex-direction: column;
  gap: 10px;
  background-color: #ffffff;
  padding: 30px;
  width: min(450px, 100%);
  border-radius: 20px;
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
}

::placeholder {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Oxygen, Ubuntu, Cantarell, 'Open Sans', 'Helvetica Neue', sans-serif;
}

.form button {
  align-self: flex-end;
}

.inputForm {
  border: 1.5px solid #ecedec;
  border-radius: 10px;
  height: 50px;
  display: flex;
  align-items: center;
  padding-left: 10px;
  transition: border 0.2s ease-in-out;
  min-width: 0;
}

.inputForm svg {
  width: 20px;
  height: 20px;
  color: #151717;
  flex: 0 0 auto;
}

.inputForm:focus-within {
  border: 1.5px solid #2d79f3;
}

.input {
  margin-left: 10px;
  border-radius: 10px;
  border: none;
  flex: 1;
  min-width: 0;
  height: 100%;
  appearance: none;
  background: transparent;
}

.input:focus {
  outline: none;
}

.flex-row {
  display: flex;
  flex-direction: row;
  align-items: center;
  gap: 10px;
  justify-content: space-between;
}

.flex-row > div > label {
  font-size: 14px;
  color: black;
  font-weight: 400;
}

.span {
  font-size: 14px;
  margin-left: 5px;
  color: #2d79f3;
  font-weight: 500;
  cursor: pointer;
}

.button-submit {
  margin: 20px 0 10px 0;
  background-color: #151717;
  border: none;
  color: white;
  font-size: 15px;
  font-weight: 500;
  border-radius: 10px;
  height: 50px;
  width: 100%;
  cursor: pointer;
  transition: opacity 0.2s ease-in-out;
}

.button-submit:disabled {
  opacity: 0.6;
  cursor: default;
}

.p {
  text-align: center;
  color: black;
  font-size: 14px;
  margin: 5px 0;
}

.p.line {
  margin-top: 14px;
}

.p.notice {
  color: #2d79f3;
}

.p.note-text {
  font-size: 12px;
  color: #444;
}

.error-line {
  text-align: center;
  color: #dc2626;
  font-size: 13px;
  margin: 4px 0 0;
}

.btn {
  margin-top: 10px;
  width: 100%;
  height: 50px;
  border-radius: 10px;
  display: flex;
  justify-content: center;
  align-items: center;
  font-weight: 500;
  gap: 10px;
  border: 1px solid #ededef;
  background-color: white;
  cursor: pointer;
  transition: border-color 0.2s ease-in-out;
}

.btn:hover {
  border: 1px solid #2d79f3;
}

.btn:active {
  transform: scale(0.98);
}
</style>
