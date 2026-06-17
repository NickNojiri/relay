import js from "@eslint/js";
import tseslint from "typescript-eslint";
import prettier from "eslint-config-prettier";

/** Shared flat ESLint config for all Relay TypeScript workspaces. */
export default tseslint.config(
  { ignores: ["dist/**", ".next/**", "node_modules/**", "**/*.config.*"] },
  js.configs.recommended,
  ...tseslint.configs.recommended,
  prettier,
);
