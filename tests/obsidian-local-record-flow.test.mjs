import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

import {
  MANUAL_RECORDS,
  manualRecordSource,
  safeRecordTitle,
  recordKindFromLocation,
} from '/home/neet821/Documents/Obsidian Vault/.obsidian/plugins/elysium-record-review-sync/local-record-flow.js';

const vaultRoot = '/home/neet821/Documents/Obsidian Vault';

test('all four local records produce only the requested offline frontmatter', () => {
  for (const [kind, meta] of Object.entries(MANUAL_RECORDS)) {
    const source = manualRecordSource(kind, '本地测试记录');
    assert.match(source, new RegExp(`^type: ${kind}$`, 'm'));
    assert.doesNotMatch(source, /^title:/m);
    assert.match(source, /^cover:/m);
    assert.match(source, /^year:/m);
    assert.match(source, /^review:/m);
    assert.doesNotMatch(source, /^(status|rating|source|source_id|external_url):/m);
    if (kind === 'movie') assert.match(source, /^director:/m);
    if (kind === 'movie' || kind === 'book') {
      assert.match(source, /^country:/m);
      assert.match(source, /^language:/m);
    }
    if (kind !== 'movie' && kind !== 'game') assert.match(source, /^creator:/m);
    assert.doesNotMatch(source, /https?:\/\//i);
    assert.equal(meta.folder, `资源库/记录/${meta.label}`);
  }
});

test('titles are safe file names and empty titles are rejected by the caller', () => {
  assert.equal(safeRecordTitle('  A/B: C?  '), 'A—B— C—');
  assert.equal(safeRecordTitle('...'), '未命名记录');
});

test('Bases new-note locations identify the correct kind, including books', () => {
  assert.equal(recordKindFromLocation('资源库/记录/电影'), 'movie');
  assert.equal(recordKindFromLocation('资源库/记录/专辑'), 'album');
  assert.equal(recordKindFromLocation('资源库/记录/书籍'), 'book');
  assert.equal(recordKindFromLocation('资源库/记录/游戏'), 'game');
  assert.equal(recordKindFromLocation('其他'), '');
});

test('vault templates and metadata helper contain no remote lookup path', () => {
  const files = [
    '资源库/模板/Elysium-电影.md',
    '资源库/模板/Elysium-专辑.md',
    '资源库/模板/Elysium-书籍.md',
    '资源库/模板/Elysium-游戏.md',
  ];
  for (const relative of files) {
    const source = fs.readFileSync(path.join(vaultRoot, relative), 'utf8');
    assert.doesNotMatch(source, /fetch\s*\(|XMLHttpRequest|https?:\/\//i, relative);
    assert.doesNotMatch(source, /elysiumMetadata/i, relative);
  }
});

test('native templates remain usable without the custom record plugin', () => {
  const files = [
    '资源库/模板/Elysium-电影.md',
    '资源库/模板/Elysium-专辑.md',
    '资源库/模板/Elysium-书籍.md',
    '资源库/模板/Elysium-游戏.md',
  ];
  for (const relative of files) {
    const source = fs.readFileSync(path.join(vaultRoot, relative), 'utf8');
    assert.doesNotMatch(source, /elysium-record-review-sync|data-elysium-writing-controls/i, relative);
    assert.match(source, /^review:/m, relative);
  }
  for (const relative of ['资源库/模板/Elysium-文章.md', '资源库/模板/Elysium-随笔.md']) {
    const source = fs.readFileSync(path.join(vaultRoot, relative), 'utf8');
    assert.doesNotMatch(source, /elysium-record-review-sync|data-elysium-writing-controls/i, relative);
  }
});

test('the custom record plugin is no longer active', () => {
  const enabled = JSON.parse(fs.readFileSync(
    path.join(vaultRoot, '.obsidian/community-plugins.json'),
    'utf8',
  ));
  assert.equal(enabled.includes('elysium-record-review-sync'), false);
});

test('Meta Bind provides the editor while Bases does not bypass template creation', () => {
  const base = fs.readFileSync(path.join(vaultRoot, '资源库/数据库/记录.base'), 'utf8');
  assert.equal((base.match(/titleProperty: file\.name/g) || []).length, 4);
  assert.doesNotMatch(base, /titleProperty: note\.title/);
  assert.doesNotMatch(base, /note\.(status|rating|source|source_id|external_url)/);
  for (const relative of [
    '资源库/模板/Elysium-电影.md',
    '资源库/模板/Elysium-专辑.md',
    '资源库/模板/Elysium-书籍.md',
    '资源库/模板/Elysium-游戏.md',
  ]) {
    const source = fs.readFileSync(path.join(vaultRoot, relative), 'utf8');
    assert.match(source, /^review:/m, relative);
    assert.match(source, /INPUT\[textArea:review\]/, relative);
    assert.doesNotMatch(source, /^title:/m, relative);
    assert.doesNotMatch(source, /INPUT\[text:title\]/, relative);
    assert.doesNotMatch(source, /不要直接重命名文件/, relative);
  }
});

test('native properties stay hidden and Meta Bind is the editor layer', () => {
  const app = JSON.parse(fs.readFileSync(path.join(vaultRoot, '.obsidian/app.json'), 'utf8'));
  assert.equal(app.propertiesInDocument, 'hidden');
  assert.equal(app.attachmentFolderPath, '资源库/附件');
  assert.equal(app.defaultViewMode, 'preview');
  const appearance = JSON.parse(fs.readFileSync(path.join(vaultRoot, '.obsidian/appearance.json'), 'utf8'));
  assert.equal(appearance.enabledCssSnippets.includes('hide-properties'), true);
  const metaBindManifest = JSON.parse(fs.readFileSync(
    path.join(vaultRoot, '.obsidian/plugins/obsidian-meta-bind-plugin/manifest.json'),
    'utf8',
  ));
  assert.equal(metaBindManifest.isDesktopOnly, false);
  assert.equal(metaBindManifest.id, 'obsidian-meta-bind-plugin');
  assert.equal(fs.existsSync(path.join(vaultRoot, '新建内容.md')), false);
  const creationPanelPath = path.join(vaultRoot, '资源库/新建内容.md');
  assert.equal(fs.existsSync(creationPanelPath), true);
  assert.match(fs.readFileSync(path.join(vaultRoot, '记录.md'), 'utf8'), /!\[\[资源库\/新建内容\]\]/);
  const creationPanel = fs.readFileSync(creationPanelPath, 'utf8');
  assert.doesNotMatch(creationPanel, /templaterCreateNote/);
  for (const id of ['qa-article', 'qa-essay', 'qa-movie', 'qa-album', 'qa-book', 'qa-game']) {
    assert.match(creationPanel, new RegExp(`quickadd:choice:${id}`));
  }
  for (const root of ['文章', '随笔', '资源库/记录']) {
    const files = [];
    const walk = (relative) => {
      const absolute = path.join(vaultRoot, relative);
      for (const entry of fs.readdirSync(absolute, { withFileTypes: true })) {
        const child = path.join(relative, entry.name);
        if (entry.isDirectory()) walk(child);
        else if (entry.name.endsWith('.md')) files.push(child);
      }
    };
    walk(root);
    for (const relative of files) {
      const source = fs.readFileSync(path.join(vaultRoot, relative), 'utf8');
      assert.doesNotMatch(source, /elysium-record-editor|<details class="elysium-edit-panel">/i, relative);
    }
  }
});

test('writing templates use a native cover area and collapse only the edit panel', () => {
  const article = fs.readFileSync(path.join(vaultRoot, '资源库/模板/Elysium-文章.md'), 'utf8');
  assert.match(article, /<!-- elysium-cover:start -->/);
  assert.match(article, /<!-- elysium-cover:end -->/);
  assert.doesNotMatch(article, /^##+\s+封面/m);
  assert.match(article, /\[!info\]- 编辑信息/);
  assert.doesNotMatch(article, /<details class="elysium-edit-panel">/);
  assert.match(article, /dv\.view\("资源库\/Scripts\/elysiumCover"/);
  assert.match(article, /INPUT\[textArea:preview\]/);
  assert.match(article, /同步到网站/);
  assert.doesNotMatch(article, /INPUT\[text:cover\]/);
  assert.doesNotMatch(article, /^review:/m);
  assert.doesNotMatch(article, /INPUT\[textArea:review\]/);

  const essay = fs.readFileSync(path.join(vaultRoot, '资源库/模板/Elysium-随笔.md'), 'utf8');
  assert.match(essay, /\[!info\]- 编辑信息/);
  assert.doesNotMatch(essay, /elysiumCover|封面|cover|摘要|preview|review|附加评论/);
  assert.match(essay, /INPUT\[inlineSelect\(option\(是\), option\(否\)\):同步到网站\]/);
  assert.doesNotMatch(essay, /封面|cover|摘要|preview|review|附加评论/);

  for (const relative of [
    '资源库/模板/Elysium-电影.md',
    '资源库/模板/Elysium-专辑.md',
    '资源库/模板/Elysium-书籍.md',
    '资源库/模板/Elysium-游戏.md',
  ]) {
    const source = fs.readFileSync(path.join(vaultRoot, relative), 'utf8');
    assert.match(source, /<!-- elysium-cover:start -->/, relative);
    assert.match(source, /<!-- elysium-cover:end -->/, relative);
    assert.doesNotMatch(source, /^##+\s+封面/m, relative);
    assert.match(source, /\[!info\]- 编辑信息/, relative);
    assert.doesNotMatch(source, /<details class="elysium-edit-panel">/, relative);
    assert.match(source, /dv\.view\("资源库\/Scripts\/elysiumCover"/, relative);
    assert.match(source, /INPUT\[textArea:review\]/, relative);
    assert.doesNotMatch(source, /INPUT\[text:cover\]/, relative);
    assert.doesNotMatch(source, /INPUT\[(?:inlineSelect|number).*?(?:status|rating)/, relative);
  }
});

test('QuickAdd choices ask for names, increment collisions, and open in reading mode', () => {
  const quickAdd = JSON.parse(fs.readFileSync(path.join(vaultRoot, '.obsidian/plugins/quickadd/data.json'), 'utf8'));
  const ids = ['qa-article', 'qa-essay', 'qa-movie', 'qa-album', 'qa-book', 'qa-game'];
  for (const id of ids) {
    const choice = quickAdd.choices.find((entry) => entry.id === id);
    assert.ok(choice, id);
    assert.equal(choice.fileNameFormat.format, '{{VALUE}}', id);
    assert.equal(choice.fileOpening.mode, 'preview', id);
    assert.equal(choice.fileExistsBehavior.kind, 'prompt', id);
  }
});

test('cover view is a paste-or-pick drop zone and public markers are removable', () => {
  const view = path.join(vaultRoot, '资源库/Scripts/elysiumCover.js');
  assert.equal(fs.existsSync(view), true);
  const source = fs.readFileSync(view, 'utf8');
  assert.match(source, /navigator\.clipboard|clipboard/i);
  assert.match(source, /资源库\/附件/);
  assert.match(source, /cover/);
  assert.match(source, /paste|drop|file/i);
});
