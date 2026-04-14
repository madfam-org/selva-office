/**
 * Development-only logger utility.
 *
 * Wraps console methods so that warnings and errors are suppressed in
 * production builds.  In development the output is identical to using
 * console directly.
 */

const isDev = process.env.NODE_ENV === 'development';

export const logger = {
  warn: (...args: unknown[]): void => {
    if (isDev) console.warn(...args);
  },
  error: (...args: unknown[]): void => {
    if (isDev) console.error(...args);
  },
  info: (...args: unknown[]): void => {
    if (isDev) console.info(...args);
  },
  debug: (...args: unknown[]): void => {
    if (isDev) console.debug(...args);
  },
};
