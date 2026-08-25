import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';

const source = readFileSync(new URL('../src/main.js', import.meta.url), 'utf8');
const styles = readFileSync(new URL('../src/styles.css', import.meta.url), 'utf8');

describe('single-page article homepage', () => {
  it('interleaves articles, essays, and records in one feed', () => {
    expect(source).toContain("['article', 'essay', 'record'].includes(article.contentType)");
    expect(source).toContain("article.type === 'essay'");
    expect(source).toContain('recordCard(article)');
  });

  it('inserts the photo strip after the first two feed entries', () => {
    expect(source).toContain('index === 2 ? strip :');
    expect(source).toContain('function photoStrip(photos)');
  });

  it('keeps photos inside the content flow instead of a right sidebar', () => {
    expect(source).toContain('class="photo-strip"');
    expect(styles).toMatch(/\.photo-strip-grid\s*\{[\s\S]*grid-template-columns:\s*repeat\(4/);
    expect(source).not.toContain('fixed-sidebar');
  });
});
