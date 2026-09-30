import { defineConfig } from "vite";
import react from "@vitejs/plugin-react";

// The deployable contract and the deployment record live outside this folder,
// in contracts/build and deploy/. They are imported directly so the UI can
// never ship a contract that differs from the one the tests verified.
export default defineConfig({
  plugins: [react()],
  // Relative asset paths: the site uses hash routing, so the same build works
  // at a domain root or under a project path such as GitHub Pages.
  base: "./",
  server: { fs: { allow: [".."] } },
  build: { target: "es2022", chunkSizeWarningLimit: 1500 },
});
