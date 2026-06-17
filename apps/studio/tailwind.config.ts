import type { Config } from "tailwindcss";
import sharedConfig from "@relay/ui/tailwind.config.ts";

// Reuse the design-system tokens from @relay/ui; only override the content globs.
const config: Config = {
  presets: [sharedConfig],
  content: [
    "./app/**/*.{ts,tsx}",
    "../../packages/ui/src/**/*.{ts,tsx}",
  ],
};

export default config;
