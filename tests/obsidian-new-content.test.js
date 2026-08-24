import { existsSync, readFileSync } from 'node:fs';
import { describe, expect, test } from 'vitest';

const vault = '/home/neet821/Documents/Obsidian Vault';
const recordIndex = readFileSync(`${vault}/记录.md`, 'utf8');
const cmdr = JSON.parse(readFileSync(`${vault}/.obsidian/plugins/cmdr/data.json`, 'utf8'));
const quickAdd = JSON.parse(readFileSync(`${vault}/.obsidian/plugins/quickadd/data.json`, 'utf8'));
const appearance = JSON.parse(readFileSync(`${vault}/.obsidian/appearance.json`, 'utf8'));
const toolbarCss = readFileSync(`${vault}/.obsidian/snippets/hide-bases-toolbar-actions.css`, 'utf8');
const templateNames = [
  'Elysium-电影.md',
  'Elysium-专辑.md',
  'Elysium-书籍.md',
  'Elysium-游戏.md',
];

describe('Obsidian new content panel', () => {
  test('sidebar quick create points to an enabled native command', () => {
    const quickCreate = cmdr.leftRibbon.find((item) => item.name === '快速创建');
    expect(quickCreate).toBeDefined();
    expect(quickCreate.id).toBe('quickadd:choice:qa-quick-create-six');
    expect(quickCreate.id).not.toContain('elysium-record-review-sync');
  });

  test('sidebar quick create contains only six new-note choices', () => {
    const choice = quickAdd.choices.find((item) => item.id === 'qa-quick-create-six');
    expect(choice?.type).toBe('Multi');
    expect(choice.choices.map((item) => item.name)).toEqual([
      '新建文章', '新建随笔', '新建电影记录', '新建专辑记录', '新建书籍记录', '新建游戏记录',
    ]);
  });

  test('only exposes the four record creation buttons', () => {
    expect(recordIndex).toContain("['新建电影记录'");
    expect(recordIndex).toContain("['新建专辑记录'");
    expect(recordIndex).toContain("['新建书籍记录'");
    expect(recordIndex).toContain("['新建游戏记录'");
    expect(recordIndex).not.toContain("['新建文章'");
    expect(recordIndex).not.toContain("['新建随笔'");
    expect(recordIndex).toContain('new-content-buttons');
    expect(recordIndex).not.toContain('## 新建内容');
    expect(existsSync(`${vault}/资源库/新建内容.md`)).toBe(false);
  });

  test('hides only the requested page title and Bases toolbar actions', () => {
    expect(appearance.enabledCssSnippets).toContain('hide-bases-toolbar-actions');
    expect(toolbarCss).toContain('.bases-toolbar-filter');
    expect(toolbarCss).toContain('[class*="toolbar-filter"]');
    expect(toolbarCss).toContain('.bases-toolbar-properties');
    expect(toolbarCss).toContain('.bases-toolbar-new-item-menu');
    expect(toolbarCss).not.toContain('.bases-toolbar-search');
    expect(toolbarCss).not.toContain('.bases-toolbar-sort');
  });

  test('record templates use QuickAdd date placeholders', () => {
    for (const name of templateNames) {
      const template = readFileSync(`${vault}/资源库/模板/${name}`, 'utf8');
      expect(template).toContain('{{DATE:YYYY-MM-DDTHH:mm:ssZ}}');
      expect(template).not.toContain('<% tp.date.now');
    }
  });

  test('existing records do not contain unevaluated date code', () => {
    const recordFiles = [
      '资源库/记录/电影/大的放.md',
      '资源库/记录/专辑/成都市风格.md',
      '资源库/记录/书籍/反而啊.md',
      '资源库/记录/游戏/恩爱放.md',
    ];
    for (const path of recordFiles) {
      if (!existsSync(`${vault}/${path}`)) continue;
      const content = readFileSync(`${vault}/${path}`, 'utf8');
      expect(content).not.toContain('<% tp.date.now');
      expect(content).toMatch(/created_at:\s*"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}\+08:00"/);
    }
  });
});
