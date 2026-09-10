import pluginVue from 'eslint-plugin-vue'
import tseslint from 'typescript-eslint'

/**
 * 与 `apps/web/eslint.config.js` 同构（docs/50 §11.1）：
 * 同样的 flat config 骨架、同样的行数/语句数硬约束，让两端代码风格不产生第二套标准。
 */
export default tseslint.config(
  {
    ignores: ['dist/**', 'node_modules/**', 'coverage/**'],
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
      // 单文件 ≤350 行（skip 空行/注释）、函数体 ≤60 条语句（同 apps/web）
      'max-lines': ['error', { max: 350, skipBlankLines: true, skipComments: true }],
      'max-statements': ['error', { max: 60 }],
    },
  },
  {
    // 灰名单：图表组件是"一个图型一个文件"的完整实现（几何 + 动画 + 热区），
    // 拆文件会破坏 lieflat 模板一对一可追溯性（docs/50 §12），故豁免行数限制。
    files: ['src/components/charts/**/*.vue'],
    rules: { 'max-lines': 'off' },
  },
)
