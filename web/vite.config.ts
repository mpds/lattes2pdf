import { defineConfig } from 'vite';
import { compilerCsp } from './scripts/compiler-csp.ts';
export default defineConfig({
  base: '/lattes2pdf/',
  server: { host: '127.0.0.1' },
  preview: { host: '127.0.0.1' },
  worker: {
    plugins: () => [compilerCsp()],
    format: 'es',
    rolldownOptions: { output: { codeSplitting: false } },
  },
  build: { sourcemap: false },
});
