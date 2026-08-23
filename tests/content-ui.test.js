import { describe, expect, it } from 'vitest';
import { buildCategoryNav, renderContentCard } from '../src/main.js';

describe('content website navigation', () => {
  it('shows the four public content categories', () => {
    const html = buildCategoryNav([
      { id: 'article', label: '文章', items: [] },
      { id: 'essay', label: '随笔', items: [] },
      { id: 'photo', label: '照片', items: [] },
      { id: 'record', label: '记录', items: [] },
    ]);

    expect(html).toContain('href="/content/article"');
    expect(html).toContain('href="/content/essay"');
    expect(html).toContain('href="/content/photo"');
    expect(html).toContain('href="/content/record"');
  });

  it('links a card to a type-specific detail page', () => {
    const html = renderContentCard({ contentType: 'photo', slug: '照片/夏日', title: '夏日', cover: '' });
    expect(html).toContain('/content/photo/%E7%85%A7%E7%89%87%2F%E5%A4%8F%E6%97%A5');
    expect(html).toContain('夏日');
  });
});
