import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

export default defineConfig({
  plugins: [react()],
  server: { port: 5173 },
  // Power Apps Code Apps serve the bundle from a relative path, not the domain root.
  base: "./",
  build: { outDir: "dist", sourcemap: true },
});
