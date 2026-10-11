import { fileURLToPath } from "node:url";
import { defineConfig } from "vitest/config";

// Unit tests for the frontend's pure logic (motion presets, status registry, design-token contrast, hooks' stores).
// vitest itself is the repo root's devDependency: npm puts ../node_modules/.bin on the PATH of `npm run test:unit`.
export default defineConfig({
  resolve: {
    alias: { "@": fileURLToPath(new URL("./src", import.meta.url)) },
  },
  test: {
    environment: "node",
    include: ["src/**/*.test.ts"],
  },
});
