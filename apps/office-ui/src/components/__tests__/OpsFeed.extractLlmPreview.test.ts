import { describe, it, expect } from 'vitest';
import { extractLlmPreview } from '../OpsFeed';

describe('extractLlmPreview', () => {
  it('returns null for null payload', () => {
    expect(extractLlmPreview(null)).toBeNull();
  });

  it('returns null for payload with no recognized fields', () => {
    expect(extractLlmPreview({ provider: 'anthropic', model: 'claude-3-7-sonnet' })).toBeNull();
  });

  it('picks `response_text` with a `response` label', () => {
    const r = extractLlmPreview({ response_text: 'hello world' });
    expect(r).toEqual({ label: 'response', text: 'hello world' });
  });

  it('prefers response_text over content when both present', () => {
    const r = extractLlmPreview({
      response_text: 'canonical response',
      content: 'legacy field',
    });
    expect(r?.text).toBe('canonical response');
  });

  it('falls back to `content` when response_text absent', () => {
    const r = extractLlmPreview({ content: 'via content field' });
    expect(r).toEqual({ label: 'response', text: 'via content field' });
  });

  it('falls back to `text` / `output` for response-side fields', () => {
    expect(extractLlmPreview({ text: 'via text' })?.text).toBe('via text');
    expect(extractLlmPreview({ output: 'via output' })?.text).toBe('via output');
  });

  it('picks `prompt_snippet` / `prompt` / `input` with a `prompt` label', () => {
    expect(extractLlmPreview({ prompt_snippet: 'p' })).toEqual({ label: 'prompt', text: 'p' });
    expect(extractLlmPreview({ prompt: 'q' })).toEqual({ label: 'prompt', text: 'q' });
    expect(extractLlmPreview({ input: 'r' })).toEqual({ label: 'prompt', text: 'r' });
  });

  it('skips non-string payload values', () => {
    expect(
      extractLlmPreview({
        response_text: 42,
        content: null,
        text: undefined,
      }),
    ).toBeNull();
  });

  it('skips whitespace-only strings', () => {
    expect(extractLlmPreview({ response_text: '   \n  ' })).toBeNull();
  });

  it('trims leading/trailing whitespace before truncating', () => {
    const r = extractLlmPreview({ response_text: '   padded   ' });
    expect(r?.text).toBe('padded');
  });

  it('truncates strings over 280 chars and appends ellipsis', () => {
    const long = 'x'.repeat(400);
    const r = extractLlmPreview({ response_text: long });
    expect(r?.text.length).toBe(281); // 280 + ellipsis char
    expect(r?.text.endsWith('…')).toBe(true);
  });

  it('does not truncate strings at exactly the 280-char limit', () => {
    const exact = 'y'.repeat(280);
    const r = extractLlmPreview({ response_text: exact });
    expect(r?.text).toBe(exact);
    expect(r?.text.endsWith('…')).toBe(false);
  });

  it('preserves non-ASCII characters intact', () => {
    const r = extractLlmPreview({ response_text: 'Hóla — cómo estás?' });
    expect(r?.text).toBe('Hóla — cómo estás?');
  });
});
