import js from "@eslint/js";
import tseslint from "typescript-eslint";
import reactHooks from "eslint-plugin-react-hooks";
import reactRefresh from "eslint-plugin-react-refresh";
import globals from "globals";

export default tseslint.config(
  // 构建产物与依赖不参与 lint；vite.config.js/.d.ts 是 tsc -b 的编译产物
  { ignores: ["dist", "node_modules", "vite.config.js", "vite.config.d.ts"] },
  {
    extends: [js.configs.recommended, ...tseslint.configs.recommended],
    files: ["**/*.{ts,tsx}"],
    languageOptions: {
      ecmaVersion: 2020,
      globals: globals.browser,
    },
    plugins: {
      "react-hooks": reactHooks,
      "react-refresh": reactRefresh,
    },
    rules: {
      ...reactHooks.configs.recommended.rules,
      // Provider + useXxx hook 同文件导出是本项目的刻意约定（Context 模式），
      // Fast-refresh 降级可接受，不为它拆文件。
      "react-refresh/only-export-components": "off",
      // 未使用变量必须处理：用 _ 前缀显式声明意图
      "@typescript-eslint/no-unused-vars": [
        "error",
        { argsIgnorePattern: "^_", varsIgnorePattern: "^_" },
      ],
      // any 禁止：与 tsconfig strict 全开的基调一致
      "@typescript-eslint/no-explicit-any": "error",
    },
  }
);
