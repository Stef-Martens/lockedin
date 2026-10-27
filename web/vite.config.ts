import react from "@vitejs/plugin-react";
import { defineConfig } from "vite";

export default defineConfig({
  plugins: [react()],
  envDir: "..",
  server: {
    port: 5173,
    proxy: { "/api": "http://127.0.0.1:8000" },
  },
  build: {
    rollupOptions: {
      // React gets its own chunk: otherwise rollup folds it into `charts` (recharts depends on it), and the
      // app shell would have to download recharts before the first paint.
      output: { manualChunks: { react: ["react", "react-dom", "react-router-dom"], charts: ["recharts"], supabase: ["@supabase/supabase-js"] } },
    },
  },
  test: { environment: "node" },
});
