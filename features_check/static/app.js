const $ = id => document.getElementById(id);
let data, current = null, busy = false, pictureVersion = 0, preloads = [];
const row = () => current === null ? null : data.rows[current];
const dirty = () => row() && $('value').value !== row().value;
function matches(r) { return $('filter').value === 'all' || ($('filter').value === 'empty' ? !r.value.trim() : !!r.value.trim()); }
function indices() { return data.rows.map((r, i) => matches(r) ? i : -1).filter(i => i >= 0); }
function status(message, error = false) { $('status').textContent = message; $('status').className = error ? 'error' : ''; }
function allowNavigation() { return !dirty() || confirm('当前修改尚未保存，放弃修改并继续？'); }
function imageUrl(value) { try { const u = new URL(value); return ['https:', 'http:'].includes(u.protocol) ? u.href : null; } catch { return null; } }
function loadImage() {
  const version = ++pictureVersion, url = imageUrl(row().image);
  const img = $('image'); img.hidden = true; img.removeAttribute('src'); $('image-link').removeAttribute('href');
  $('image-status').textContent = url ? '图片加载中…' : '图片 URL 为空或无效';
  $('retry').disabled = !url;
  if (!url) return;
  const loader = new Image(); loader.referrerPolicy = 'no-referrer';
  loader.onload = () => { if (version !== pictureVersion) return; img.src = url; img.hidden = false; $('image-link').href = url; $('image-status').textContent = ''; };
  loader.onerror = () => { if (version === pictureVersion) $('image-status').textContent = '图片加载失败，可重试或跳过当前角色。'; };
  loader.src = url;
}
function highlight() { document.querySelectorAll('[data-value]').forEach(b => b.classList.toggle('selected', b.dataset.value === $('value').value)); }
function render() {
  const ids = indices();
  $('editor').hidden = current === null; $('empty').hidden = current !== null;
  if (current === null) { ++pictureVersion; return; }
  const r = row(), pos = ids.indexOf(current);
  $('name').textContent = r.name || '（角色名称为空）'; $('subject').textContent = '所属动漫：' + (r.subject || '（未填写）');
  $('position').textContent = `原始序号 ${r.index} / ${data.rows.length} · 筛选结果 ${pos + 1} / ${ids.length}`;
  $('jump').value = r.index; $('value').value = r.value;
  $('previous').disabled = pos <= 0; $('next').disabled = pos >= ids.length - 1;
  highlight(); loadImage();
  preloads = ids.slice(pos + 1, pos + 3).map(i => { const p = new Image(); p.referrerPolicy = 'no-referrer'; const u = imageUrl(data.rows[i].image); if (u) p.src = u; return p; });
}
function navigate(offset) { if (busy || !allowNavigation()) return; const ids = indices(), target = ids[ids.indexOf(current) + offset]; if (target !== undefined) { current = target; render(); status('已切换角色'); } }
let oldFilter = 'all';
$('filter').onchange = () => { if (!data || busy || !allowNavigation()) { $('filter').value = oldFilter; return; } oldFilter = $('filter').value; const ids = indices(); if (!ids.includes(current)) current = ids[0] ?? null; render(); status('已更新筛选'); };
$('jump-form').onsubmit = e => { e.preventDefault(); if (busy || !data) return; const index = Number($('jump').value) - 1; if (!Number.isInteger(index) || index < 0 || index >= data.rows.length) return status('序号超出范围', true); if (!allowNavigation()) return; if (!matches(data.rows[index])) { $('filter').value = oldFilter = 'all'; } current = index; render(); status('已跳转至指定角色'); };
$('previous').onclick = () => navigate(-1); $('next').onclick = () => navigate(1);
$('retry').onclick = loadImage;
$('value').oninput = () => { highlight(); status(dirty() ? '有未保存修改' : '当前值已保存'); };
document.querySelectorAll('[data-value]').forEach(b => b.onclick = () => { $('value').value = b.dataset.value; $('value').dispatchEvent(new Event('input')); });
$('save').onclick = async () => {
  if (busy || current === null) return;
  const savedIndex = current, value = $('value').value, before = indices(), position = before.indexOf(current);
  busy = true; document.querySelectorAll('button,input,select').forEach(el => el.disabled = true); status('正在写入 CSV…');
  try {
    const response = await fetch('/api/save', {method:'POST', headers:{'Content-Type':'application/json','X-Editor-Token':window.editorToken}, body:JSON.stringify({index:row().index, value, revision:data.revision})});
    const result = await response.json(); if (!response.ok) throw new Error(result.error || '保存失败');
    data.revision = result.revision; data.rows[savedIndex].value = value;
    const after = indices();
    current = before.slice(position + 1).find(i => after.includes(i)) ?? (after.includes(savedIndex) ? savedIndex : after[0] ?? null);
    render(); status(current === savedIndex ? '已写入 CSV，已到达当前筛选的最后一位。' : '已写入 CSV');
  } catch (error) { status(error.message + '；输入内容已保留。若连接中断，请刷新并核对 CSV。', true); }
  finally { busy = false; document.querySelectorAll('button,input,select').forEach(el => el.disabled = false); const ids = indices(), pos = ids.indexOf(current); $('previous').disabled = pos <= 0; $('next').disabled = pos < 0 || pos >= ids.length - 1; }
};
document.addEventListener('keydown', e => { if (e.key === 'Enter' && e.target === $('value') && !e.isComposing) { e.preventDefault(); $('save').click(); } });
window.addEventListener('beforeunload', e => { if (busy || dirty()) { e.preventDefault(); e.returnValue = ''; } });
fetch('/api/data').then(r => { if (!r.ok) throw new Error('读取失败'); return r.json(); }).then(result => { data = result; $('file').textContent = data.file; $('column').textContent = '当前属性：' + data.column; $('jump').max = data.rows.length; current = data.rows.length ? 0 : null; render(); status(`已加载 ${data.rows.length} 位角色，每次保存直接更新原 CSV。`); }).catch(e => status(e.message, true));
