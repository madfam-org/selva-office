import { configDefaults, defineConfig } from 'vitest/config';

export default defineConfig({
  test: {
    // `tsc` emits the compiled tests into dist/, and Vitest 3+ no longer
    // excludes dist/ by default, so every test would run twice (and the
    // compiled copy fails to resolve its sources).
    exclude: [...configDefaults.exclude, '**/dist/**'],
  },
});
