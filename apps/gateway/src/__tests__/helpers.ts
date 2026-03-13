import { vi } from "vitest";
import type pino from "pino";

/**
 * Creates a silent mock pino logger for tests.
 * All log methods are vi.fn() stubs that do nothing.
 */
export function mockLogger(): pino.Logger {
  const noop = vi.fn();
  const logger = {
    info: noop,
    warn: noop,
    error: noop,
    debug: noop,
    trace: noop,
    fatal: noop,
    child: () => mockLogger(),
    level: "silent",
    silent: noop,
  } as unknown as pino.Logger;

  return logger;
}
