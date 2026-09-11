import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

export default tseslint.config(
  {
    ignores: [
      'dist/**',
      'node_modules/**',
      'coverage/**',
      // Vite 依赖预打包缓存（`pnpm dev` / `vitest` 生成）：构建产物，非源码。
      // 不忽略会让"起过 dev server 的人"跑 lint 时多出一批与本次改动无关的错误。
      '.vite/**',
      // 生成物（gen:api 再生成；lint 噪声，不设行为准则）
      'src/api/generated/**',
    ],
  },
  ...tseslint.configs.recommended,
  ...pluginVue.configs['flat/recommended'],
  {
    files: ['src/**/*.vue'],
    languageOptions: {
      parserOptions: {
        parser: tseslint.parser,
      },
    },
    rules: {
      'vue/multi-word-component-names': 'off',
      'vue/singleline-html-element-content-newline': 'off',
      'vue/max-attributes-per-line': 'off',
    },
  },
  {
    rules: {
      '@typescript-eslint/no-explicit-any': 'warn',
      // fe-08（2026-09-09）：单文件 ≤350 行（skip 空行/注释）、函数体 ≤60 条语句——
      // 超限存量文件走下方灰名单（新代码不豁免，重架构时摘名单）
      'max-lines': ['error', { max: 350, skipBlankLines: true, skipComments: true }],
      'max-statements': ['error', { max: 60 }],
    },
  },
  {
    // 灰名单（fe-08）：存量超限文件（350 行约定落地时已是历史行数；重构摘除后删除本组）
    files: [
      'src/views/mobile/MobileSpeakingView.vue',
      'src/views/mobile/MobileFreeChatView.vue',
      'src/views/LoginView.vue',
      'src/views/PracticeView.vue',
      'src/views/preview/FluencyPreview.vue',
      'src/views/preview/uic/UicHome.vue',
      'src/views/preview/uic/UicSinging.vue',
      'src/views/preview/uic/UicSpeaking.vue',
    ],
    rules: { 'max-lines': 'off' },
  },
  {
    // 灰名单（fe-08）：函数体语句超限存量文件（开关型 onSseEvent/~setup 函数）
    files: [
      'src/views/mobile/MobileSpeakingView.vue',
      'src/views/mobile/MobileFreeChatView.vue',
      'src/views/LoginView.vue',
      'src/views/PracticeView.vue',
      'src/views/preview/FluencyPreview.vue',
    ],
    rules: { 'max-statements': 'off' },
  },
)
