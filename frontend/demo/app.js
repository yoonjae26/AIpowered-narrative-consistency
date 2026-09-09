'use strict';
// ── Config ──────────────────────────────────────────────────
const API = 'http://localhost:8001';

// ── State ───────────────────────────────────────────────────
const state = {
  docs: [],
  activeDoc: null,
  categoryFilter: '',
  sortOrder: 'latest',
  rpPage: 0,
  rpSections: [],
  qaMessages: [],
  conMessages: [],
};

// ── Helpers ─────────────────────────────────────────────────
const $ = (s, el = document) => el.querySelector(s);
const $$ = (s, el = document) => [...el.querySelectorAll(s)];
const esc = (s) => String(s ?? '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

function now() {
  return new Date().toLocaleTimeString('ko-KR', { hour: '2-digit', minute: '2-digit', hour12: false });
}

async function api(path, opts = {}) {
  const res = await fetch(API + path, {
    headers: { 'Content-Type': 'application/json', ...(opts.headers || {}) },
    ...opts,
  });
  if (!res.ok) throw new Error(`${res.status} ${await res.text()}`);
  return res.json();
}

// ── File type detection ──────────────────────────────────────
function fileTypeClass(name = '') {
  const ext = name.split('.').pop().toLowerCase();
  const map = { docx: 'docx', doc: 'docx', pdf: 'pdf', xlsx: 'xlsx', xls: 'xlsx', md: 'md', txt: 'txt', zip: 'zip' };
  return map[ext] || 'txt';
}

function fileTypeLabel(name = '') {
  const ext = name.split('.').pop().toUpperCase();
  return ext.slice(0, 4);
}

// ── Category badge ───────────────────────────────────────────
const CATS = ['세계관', '캐릭터', '원고', '연표', '기준문서', '메모'];

function categoryClass(cat) {
  return CATS.includes(cat) ? `cat-${cat}` : 'cat-default';
}

// ── Document list rendering ──────────────────────────────────
function renderDocList() {
  const list = $('#docList');
  let docs = state.docs.filter(d => !state.categoryFilter || d.category === state.categoryFilter);

  if (state.sortOrder === 'name') {
    docs = docs.slice().sort((a, b) => a.name.localeCompare(b.name, 'ko'));
  }

  if (!docs.length) {
    list.innerHTML = `<div class="doc-loading" style="flex-direction:column;align-items:center;color:var(--t4);padding:30px 0;">
      <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/><polyline points="14 2 14 8 20 8"/></svg>
      <span style="margin-top:8px;font-size:12.5px;">문서가 없습니다</span>
    </div>`;
    return;
  }

  list.innerHTML = docs.map(doc => {
    const dbSources = ['characters_db', 'scenes_db'];
    const typeClass = dbSources.includes(doc.source) ? 'type-db' : `type-${fileTypeClass(doc.name)}`;
    const label = dbSources.includes(doc.source) ? 'DB' : fileTypeLabel(doc.name);
    const catClass = categoryClass(doc.category);
    const isSelected = state.activeDoc && state.activeDoc.id === doc.id;

    return `<div class="doc-item ${isSelected ? 'selected' : ''}" data-id="${esc(doc.id)}">
      <div class="doc-checkbox ${doc.selected ? 'checked' : ''}" data-check="${esc(doc.id)}"></div>
      <div class="doc-file-icon ${typeClass}">${esc(label)}</div>
      <div class="doc-info">
        <div class="doc-name">${esc(doc.name)}</div>
        <div class="doc-meta">${esc(doc.time_label)} · ${esc(doc.size_label)}</div>
      </div>
      <button class="doc-category-badge ${catClass}" data-cat-btn="${esc(doc.id)}">${esc(doc.category)}
        <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="6 9 12 15 18 9"/></svg>
      </button>
      <button class="doc-more-btn" data-more="${esc(doc.id)}">···</button>
    </div>`;
  }).join('');

  $('#docCount').textContent = `문서 목록 (${docs.length})`;

  // bind events
  $$('.doc-item').forEach(el => {
    el.addEventListener('click', (e) => {
      if (e.target.closest('[data-check]') || e.target.closest('[data-cat-btn]') || e.target.closest('[data-more]')) return;
      const id = el.dataset.id;
      openDocInspector(id);
    });
  });

  $$('[data-check]').forEach(el => {
    el.addEventListener('click', (e) => {
      e.stopPropagation();
      const id = el.dataset.check;
      const doc = state.docs.find(d => d.id === id);
      if (!doc) return;
      doc.selected = !doc.selected;
      el.classList.toggle('checked', doc.selected);
      const autoSources = ['characters_db', 'scenes_db', 'source_file'];
      if (!autoSources.includes(doc.source)) {
        api(`/documents/${id}/select?selected=${doc.selected}`, { method: 'PATCH' }).catch(() => {});
      }
    });
  });

  $$('[data-cat-btn]').forEach(btn => {
    btn.addEventListener('click', (e) => {
      e.stopPropagation();
      showCategoryPopover(btn, btn.dataset.catBtn);
    });
  });
}

// ── Category popover ─────────────────────────────────────────
let popoverTarget = null;
function showCategoryPopover(btn, docId) {
  const pop = $('#categoryPopover');
  popoverTarget = docId;
  pop.classList.add('open');
  const rect = btn.getBoundingClientRect();
  pop.style.top = (rect.bottom + 4) + 'px';
  pop.style.left = rect.left + 'px';
}

function hideCategoryPopover() {
  $('#categoryPopover').classList.remove('open');
  popoverTarget = null;
}

document.addEventListener('click', (e) => {
  if (!e.target.closest('.category-popover') && !e.target.closest('[data-cat-btn]')) {
    hideCategoryPopover();
  }
});

$$('#categoryPopover button').forEach(btn => {
  btn.addEventListener('click', async () => {
    if (!popoverTarget) return;
    const cat = btn.dataset.cat;
    const doc = state.docs.find(d => d.id === popoverTarget);
    if (!doc) return;
    doc.category = cat;
    hideCategoryPopover();
    renderDocList();
    const autoSources2 = ['characters_db', 'scenes_db', 'source_file'];
    if (!autoSources2.includes(doc.source)) {
      try { await api(`/documents/${doc.id}/category?category=${encodeURIComponent(cat)}`, { method: 'PATCH' }); } catch (_) {}
    }
  });
});

// ── Load documents ───────────────────────────────────────────
async function loadDocuments() {
  try {
    const docs = await api('/documents');
    state.docs = docs;
    renderDocList();
    renderRecentDocs();
  } catch (e) {
    $('#docList').innerHTML = `<div class="doc-loading" style="color:var(--sem-error-t)">로드 실패: ${esc(e.message)}</div>`;
  }
}

// ── File upload ──────────────────────────────────────────────
async function uploadFile(file) {
  const form = new FormData();
  form.append('file', file);
  form.append('category', '메모');

  const res = await fetch(`${API}/documents/upload`, { method: 'POST', body: form });
  if (!res.ok) throw new Error(await res.text());
  const doc = await res.json();
  state.docs.unshift(doc);
  renderDocList();
}

// Upload zone events
const uploadZone = $('#uploadZone');
const fileInput = $('#fileInput');

uploadZone.addEventListener('click', () => fileInput.click());
uploadZone.addEventListener('dragover', (e) => { e.preventDefault(); uploadZone.classList.add('drag-over'); });
uploadZone.addEventListener('dragleave', () => uploadZone.classList.remove('drag-over'));
uploadZone.addEventListener('drop', async (e) => {
  e.preventDefault();
  uploadZone.classList.remove('drag-over');
  const files = [...e.dataTransfer.files];
  for (const f of files) {
    try { await uploadFile(f); } catch (err) { console.error('Upload failed:', err); }
  }
});

fileInput.addEventListener('change', async () => {
  const files = [...fileInput.files];
  for (const f of files) {
    try { await uploadFile(f); } catch (err) { console.error('Upload failed:', err); }
  }
  fileInput.value = '';
});

$('#attachBtn').addEventListener('click', () => fileInput.click());

// ── Document inspector (right panel) ─────────────────────────
async function openDocInspector(docId) {
  const doc = state.docs.find(d => d.id === docId);
  if (!doc) return;
  state.activeDoc = doc;
  renderDocList();

  const body = $('#body');
  body.classList.add('has-inspector');

  $('#rpTitle').textContent = doc.name;
  const sourceLabels = { characters_db: '데이터베이스 · 캐릭터', scenes_db: '데이터베이스 · 장면', source_file: '원본 파일 · honggildongjeon.txt' };
  $('#rpFilePath').textContent = sourceLabels[doc.source] || `파일 위치: ${doc.name}`;
  $('#rpSections').innerHTML = `<div class="doc-loading"><div class="spinner-sm"></div>불러오는 중...</div>`;
  $('#rpSummary').innerHTML = `<div class="rp-empty">로딩 중...</div>`;

  state.rpPage = 0;

  try {
    const detail = await api(`/documents/${docId}`);
    state.rpSections = detail.sections || [];
    renderRpPage();
    renderRpSummary(detail);
    updateRpPagination();
  } catch (e) {
    $('#rpSections').innerHTML = `<div class="rp-empty" style="color:var(--sem-error-t)">로드 실패</div>`;
  }
}

function closeInspector() {
  state.activeDoc = null;
  state.rpSections = [];
  state.rpPage = 0;
  $('#body').classList.remove('has-inspector');
  renderDocList();
}

function renderRpPage() {
  const sections = state.rpSections;
  if (!sections.length) {
    $('#rpSections').innerHTML = '<div class="rp-empty">섹션이 없습니다.</div>';
    return;
  }

  const perPage = 1;
  const page = state.rpPage;
  const sec = sections[page];
  if (!sec) return;

  let html = '<div class="rp-section">';

  if (sec.fields) {
    // Character-style section with labeled fields
    html += `<div class="rp-section-title">${esc(sec.title)}</div>`;
    for (const f of sec.fields) {
      const hi = f.highlight ? ' highlighted' : '';
      html += `<div class="rp-field">
        <div class="rp-field-label">${esc(f.label)}</div>
        <div class="rp-field-value${hi}">${esc(f.value)}</div>
      </div>`;
    }
  } else {
    // Text-based section
    const hi = sec.highlight ? ' highlighted' : '';
    html += `<div class="rp-text-section${hi}">
      <span class="rp-text-title">${esc(sec.title)}</span>
      ${esc(sec.content || '').replace(/\n/g, '<br>')}
    </div>`;
  }

  html += '</div>';
  $('#rpSections').innerHTML = html;
}

function renderRpSummary(detail) {
  const sections = detail.sections || [];
  if (!sections.length) {
    $('#rpSummary').innerHTML = '<div class="rp-empty">요약 정보가 없습니다.</div>';
    return;
  }

  let html = '';
  for (const sec of sections.slice(0, 5)) {
    html += `<div class="rp-section">
      <div class="rp-section-title">${esc(sec.title)}</div>`;
    if (sec.fields) {
      for (const f of sec.fields.slice(0, 3)) {
        html += `<div class="rp-field">
          <div class="rp-field-label">${esc(f.label)}</div>
          <div class="rp-field-value">${esc(f.value)}</div>
        </div>`;
      }
    } else if (sec.content) {
      const preview = sec.content.slice(0, 200);
      html += `<div class="rp-field-value">${esc(preview)}${sec.content.length > 200 ? '…' : ''}</div>`;
    }
    html += `</div>`;
  }
  $('#rpSummary').innerHTML = html;
}

function updateRpPagination() {
  const total = state.rpSections.length;
  $('#rpPageInfo').textContent = total ? `${state.rpPage + 1} / ${total}` : '0 / 0';
}

$('#rpPrev').addEventListener('click', () => {
  if (state.rpPage > 0) { state.rpPage--; renderRpPage(); updateRpPagination(); }
});
$('#rpNext').addEventListener('click', () => {
  if (state.rpPage < state.rpSections.length - 1) { state.rpPage++; renderRpPage(); updateRpPagination(); }
});

$('#rpClose').addEventListener('click', closeInspector);
$('#rpBack').addEventListener('click', closeInspector);

// RP tabs
$$('.rp-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    $$('.rp-tab').forEach(t => t.classList.remove('active'));
    $$('.rp-tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    $('#rptab-' + tab.dataset.rptab).classList.add('active');
  });
});

// ── Center tabs ──────────────────────────────────────────────
$$('.center-tab').forEach(tab => {
  tab.addEventListener('click', () => {
    $$('.center-tab').forEach(t => t.classList.remove('active'));
    $$('.tab-content').forEach(c => c.classList.remove('active'));
    tab.classList.add('active');
    $('#tab-' + tab.dataset.tab).classList.add('active');
  });
});

// ── Filter chips ─────────────────────────────────────────────
$$('#filterChips .filter-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    $$('#filterChips .filter-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
  });
});

$$('.cat-filter-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    $$('.cat-filter-chip').forEach(c => c.classList.remove('active'));
    chip.classList.add('active');
    state.categoryFilter = chip.dataset.cat;
    renderDocList();
  });
});

// ── Q&A Chat ────────────────────────────────────────────────
function appendMessage(container, role, content, sources = [], time = now()) {
  const empty = container.querySelector('.chat-empty');
  if (empty) empty.remove();

  const div = document.createElement('div');

  if (role === 'user') {
    div.className = 'msg-user';
    div.innerHTML = `<div class="msg-bubble">${esc(content)}</div><div class="msg-time">${esc(time)}</div>`;
  } else if (role === 'loading') {
    div.className = 'msg-ai msg-loading';
    div.id = 'loadingMsg';
    div.innerHTML = `
      <div class="ai-avatar"><svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg></div>
      <div class="msg-ai-body">
        <div class="msg-ai-bubble"><div class="spinner-sm"></div>분석 중...</div>
      </div>`;
  } else {
    // AI message
    let sourcesHtml = '';
    if (sources && sources.length) {
      sourcesHtml = `<div class="msg-sources">
        <div class="msg-sources-label">근거가 된 문서</div>
        ${sources.map(s => `
          <div class="source-item">
            <span class="source-doc-name">${esc(s.doc_name)}</span>
            <span class="source-sep">›</span>
            <span class="source-section">${esc(s.section)}</span>
            <button class="source-link-btn" title="문서 열기" data-src-id="${esc(s.doc_id || '')}">
              <svg width="10" height="10" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M18 13v6a2 2 0 01-2 2H5a2 2 0 01-2-2V8a2 2 0 012-2h6"/><polyline points="15 3 21 3 21 9"/><line x1="10" y1="14" x2="21" y2="3"/></svg>
            </button>
          </div>`).join('')}
      </div>`;
    }

    div.className = 'msg-ai';
    div.innerHTML = `
      <div class="ai-avatar"><svg width="12" height="12" viewBox="0 0 24 24" fill="currentColor"><polygon points="5,3 19,12 5,21"/></svg></div>
      <div class="msg-ai-body">
        <div class="msg-ai-bubble"><p>${esc(content).replace(/\n/g, '<br>')}</p>${sourcesHtml}</div>
        <div class="msg-feedback">
          <button class="feedback-btn" title="다시 생성">
            <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>
          </button>
          <span class="feedback-label">AI 답변이 도움이 됐나요?</span>
          <div class="feedback-thumbs">
            <button class="feedback-btn" title="도움이 됐어요">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 9V5a3 3 0 00-3-3l-4 9v11h11.28a2 2 0 002-1.7l1.38-9a2 2 0 00-2-2.3H14z"/><path d="M7 22H4a2 2 0 01-2-2v-7a2 2 0 012-2h3"/></svg>
            </button>
            <button class="feedback-btn" title="도움이 안 됐어요">
              <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2"><path d="M10 15v4a3 3 0 003 3l4-9V2H5.72a2 2 0 00-2 1.7l-1.38 9a2 2 0 002 2.3H10z"/><path d="M17 2h2.67A2.31 2.31 0 0122 4v7a2.31 2.31 0 01-2.33 2H17"/></svg>
            </button>
          </div>
          <div class="msg-time">${esc(time)}</div>
        </div>
      </div>`;

    // Source link buttons open inspector
    div.querySelectorAll('[data-src-id]').forEach(btn => {
      btn.addEventListener('click', () => {
        const id = btn.dataset.srcId;
        if (id) openDocInspector(id);
      });
    });
  }

  container.appendChild(div);
  container.scrollTop = container.scrollHeight;
  return div;
}

function removeLoading(container) {
  const el = container.querySelector('#loadingMsg');
  if (el) el.remove();
}

async function sendQuery(text) {
  if (!text.trim()) return;

  const msgArea = $('#qaMessages');
  appendMessage(msgArea, 'user', text);
  appendMessage(msgArea, 'loading');

  const sendBtn = $('#qaSend');
  sendBtn.disabled = true;

  try {
    const data = await api('/narrative/query', {
      method: 'POST',
      body: JSON.stringify({ query: text }),
    });

    removeLoading(msgArea);

    // Extract answer text from response
    let answer = '';
    if (typeof data === 'string') {
      answer = data;
    } else if (data.answer) {
      answer = data.answer;
    } else if (data.response) {
      answer = data.response;
    } else if (data.result) {
      answer = data.result;
    } else if (data.message) {
      answer = data.message;
    } else {
      answer = JSON.stringify(data, null, 2);
    }

    // Build sources from characters_found or evidence
    const sources = [];
    if (data.characters_found && data.characters_found.length) {
      for (const c of data.characters_found.slice(0, 3)) {
        sources.push({ doc_name: '등장인물 설정', section: c.name || c, doc_id: 'auto_characters_db' });
      }
    } else if (data.evidence && data.evidence.length) {
      for (const ev of data.evidence.slice(0, 3)) {
        // evidence items can be character objects with .name, or text-based with .text/.content
        const charName = ev.name || ev.character;
        const section = charName
          ? `${charName} 프로필`
          : (ev.text || ev.content || ev.source_scene || '').slice(0, 50);
        sources.push({
          doc_name: charName ? '등장인물 설정' : (ev.source || '문서'),
          section: section || '—',
          doc_id: charName ? 'auto_characters_db' : (ev.doc_id || ''),
        });
      }
    } else if (state.docs.length) {
      const selected = state.docs.filter(d => d.selected).slice(0, 2);
      for (const d of selected) {
        sources.push({ doc_name: d.name, section: d.category, doc_id: d.id });
      }
    }

    appendMessage(msgArea, 'ai', answer, sources);
  } catch (err) {
    removeLoading(msgArea);
    appendMessage(msgArea, 'ai', `오류가 발생했습니다: ${err.message}`, []);
  } finally {
    sendBtn.disabled = false;
  }
}

// QA input events
$('#qaInput').addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && !e.shiftKey) {
    e.preventDefault();
    const val = $('#qaInput').value.trim();
    if (val) { sendQuery(val); $('#qaInput').value = ''; }
  }
});

$('#qaSend').addEventListener('click', () => {
  const val = $('#qaInput').value.trim();
  if (val) { sendQuery(val); $('#qaInput').value = ''; }
});

// Quick action chips
$$('.qa-chip').forEach(chip => {
  chip.addEventListener('click', () => {
    const q = chip.dataset.q;
    sendQuery(q);
  });
});

// ── Consistency Check ─────────────────────────────────────────

function _issueTypeLabel(code) {
  const map = {
    opposite_absolutes: '표현 충돌', many_references: '참고',
    character_relationship_conflict: '인물 관계', relationship_conflict: '관계 충돌',
    age_conflict: '나이 충돌', timeline_conflict: '연표 충돌',
  };
  if (map[code]) return map[code];
  return code ? code.replace(/_/g, ' ') : '일관성';
}

function _buildConsistencyResultSection(issues) {
  const errorCount = issues.filter(i => i.severity === 'error').length;
  const warnCount  = issues.filter(i => i.severity === 'warning').length;
  const infoCount  = issues.filter(i => i.severity === 'info').length;

  const chipsHtml = `
    <div class="con-res-chips">
      <span class="con-res-chip ${errorCount > 0 ? 'chip-error' : 'chip-zero'}">오류 ${errorCount}건</span>
      <span class="con-res-chip ${warnCount  > 0 ? 'chip-warn'  : 'chip-zero'}">경고 ${warnCount}건</span>
      <span class="con-res-chip ${infoCount  > 0 ? 'chip-info'  : 'chip-zero'}">참고 ${infoCount}건</span>
    </div>`;

  const SHOW = 5;
  const shown = issues.slice(0, SHOW);
  const rest  = issues.slice(SHOW);

  const rows = shown.map(iss => {
    const sevCls = iss.severity === 'error' ? 'sev-chip-error' : iss.severity === 'warning' ? 'sev-chip-warn' : 'sev-chip-info';
    const sevLbl = iss.severity === 'error' ? '높음' : iss.severity === 'warning' ? '보통' : '낮음';
    return `<tr class="con-issue-row">
      <td><span class="con-type-tag">${esc(_issueTypeLabel(iss.code))}</span></td>
      <td class="con-issue-msg-cell">${esc(iss.message)}</td>
      <td><span class="con-sev-chip ${sevCls}">${esc(sevLbl)}</span></td>
    </tr>`;
  }).join('');

  const moreRows = rest.map(iss => {
    const sevCls = iss.severity === 'error' ? 'sev-chip-error' : iss.severity === 'warning' ? 'sev-chip-warn' : 'sev-chip-info';
    const sevLbl = iss.severity === 'error' ? '높음' : iss.severity === 'warning' ? '보통' : '낮음';
    return `<tr class="con-issue-row con-issue-extra" style="display:none">
      <td><span class="con-type-tag">${esc(_issueTypeLabel(iss.code))}</span></td>
      <td class="con-issue-msg-cell">${esc(iss.message)}</td>
      <td><span class="con-sev-chip ${sevCls}">${esc(sevLbl)}</span></td>
    </tr>`;
  }).join('');

  const moreBtn = rest.length
    ? `<button class="con-more-btn" id="conIssuMoreBtn">더 많은 결과 보기 (${rest.length}) ↓</button>`
    : '';

  const bodyHtml = issues.length > 0
    ? `<div class="con-issue-table-wrap">
        <div class="con-issue-count">상세 결과 (${issues.length}건)</div>
        <div style="overflow-x:auto">
          <table class="con-issue-table">
            <thead><tr><th>유형</th><th>이슈 내용</th><th>심각도</th></tr></thead>
            <tbody>${rows}${moreRows}</tbody>
          </table>
        </div>
        ${moreBtn}
      </div>`
    : `<div class="con-ov-status-ok"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>일관성 문제가 발견되지 않았습니다.</div>`;

  return `<div class="con-res-section">
    <div class="con-res-section-head">
      <span class="con-ov-badge">A</span>
      <div>
        <div class="con-ov-card-title">일관성 검증</div>
        <div class="con-ov-card-desc">서사 내 인물, 설정, 연표의 충돌 및 모순을 탐지합니다.</div>
      </div>
    </div>
    ${chipsHtml}
    ${bodyHtml}
  </div>`;
}

function _buildRegulationResultSection(regulations) {
  const errorRegs = regulations.filter(r => r.level === 'error');
  const warnRegs  = regulations.filter(r => r.level === 'warning');

  const chipsHtml = `
    <div class="con-res-chips">
      <span class="con-res-chip ${errorRegs.length > 0 ? 'chip-error' : 'chip-zero'}">규정 위반 ${errorRegs.length}건</span>
      <span class="con-res-chip ${warnRegs.length  > 0 ? 'chip-warn'  : 'chip-zero'}">권고 사항 ${warnRegs.length}건</span>
      <span class="con-res-chip chip-zero">형식 오류 0건</span>
    </div>`;

  let bodyHtml = '';
  if (regulations.length > 0) {
    const groups = [
      { label: '규정 위반', items: errorRegs },
      { label: '권고 사항', items: warnRegs },
    ].filter(g => g.items.length > 0);

    const GSHOW = 2;
    const groupsHtml = groups.map(g => {
      const shown = g.items.slice(0, GSHOW);
      const rest  = g.items.slice(GSHOW);
      const itemsHtml = shown.map(r => {
        const evHtml = r.evidence && r.evidence.length
          ? `<div class="con-reg-evidence">${r.evidence.slice(0, 2).map(e =>
              `<span class="con-reg-ev-item">"${esc(e)}"</span>`).join('')}</div>`
          : '';
        return `<div class="con-reg-item">
          <div class="con-reg-item-main">
            <span class="con-reg-cat-badge">${esc(r.category)}</span>
            <span class="con-reg-msg">${esc(r.message)}</span>
          </div>${evHtml}
        </div>`;
      }).join('');
      const extraHtml = rest.map(r => {
        const evHtml = r.evidence && r.evidence.length
          ? `<div class="con-reg-evidence">${r.evidence.slice(0, 2).map(e =>
              `<span class="con-reg-ev-item">"${esc(e)}"</span>`).join('')}</div>`
          : '';
        return `<div class="con-reg-item con-reg-extra" style="display:none">
          <div class="con-reg-item-main">
            <span class="con-reg-cat-badge">${esc(r.category)}</span>
            <span class="con-reg-msg">${esc(r.message)}</span>
          </div>${evHtml}
        </div>`;
      }).join('');
      const moreId = `conRegMore_${g.label.replace(/ /g, '')}`;
      const moreBtn = rest.length
        ? `<button class="con-more-btn" id="${moreId}">+ ${rest.length}건 더 보기</button>`
        : '';
      return `<div class="con-reg-group">
        <div class="con-reg-group-label">${esc(g.label)} (${g.items.length})</div>
        ${itemsHtml}${extraHtml}${moreBtn}
      </div>`;
    }).join('');

    bodyHtml = `
      <div class="con-issue-count">상세 결과 (${regulations.length}건)</div>
      <div class="con-reg-groups">${groupsHtml}</div>`;
  } else {
    bodyHtml = `<div class="con-ov-status-ok"><svg width="13" height="13" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="20 6 9 17 4 12"/></svg>규정 위반이 발견되지 않았습니다.</div>`;
  }

  return `<div class="con-res-section">
    <div class="con-res-section-head">
      <span class="con-ov-badge">B</span>
      <div>
        <div class="con-ov-card-title">규정 및 내부문서 검수</div>
        <div class="con-ov-card-desc">기준 문서와 내부 가이드라인을 기반으로 규정 준수 여부를 검사합니다.</div>
      </div>
    </div>
    ${chipsHtml}
    ${bodyHtml}
  </div>`;
}

async function runConsistencyCheck(text) {
  if (!text.trim()) return;

  const overviewEl = $('#conOverview');
  const resultsEl  = $('#conResults');
  const sendBtn    = $('#consistencySend');

  overviewEl.style.display = 'none';
  resultsEl.style.display  = 'block';
  resultsEl.innerHTML = `<div class="con-loading-state"><div class="spinner-sm"></div><span>분석 중...</span></div>`;
  sendBtn.disabled = true;

  try {
    const data = await api('/consistency/check', {
      method: 'POST',
      body: JSON.stringify({ narrative: text, reference_notes: [] }),
    });

    const issues      = data.issues || [];
    const regulations = data.regulations || [];
    const totalIssues = issues.length + regulations.length;
    const sectionCount = (issues.length > 0 ? 1 : 0) + (regulations.length > 0 ? 1 : 0);

    resultsEl.innerHTML = `
      <div class="con-res-head">
        <div class="con-res-title-row">
          <span class="con-res-title">일관성 검수 결과</span>
          <span class="con-res-done-chip">검수 완료</span>
          <button class="con-res-retry" id="conRetryBtn">
            <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2.5"><polyline points="1 4 1 10 7 10"/><path d="M3.51 15a9 9 0 102.13-9.36L1 10"/></svg>
            다시 검수
          </button>
        </div>
        <p class="con-res-summary">총 ${Math.max(sectionCount, 1)}개의 영역에서 ${totalIssues}건의 이슈가 발견되었습니다.</p>
      </div>
      ${_buildConsistencyResultSection(issues)}
      ${_buildRegulationResultSection(regulations)}
    `;

    $('#conRetryBtn')?.addEventListener('click', () => {
      resultsEl.innerHTML = '';
      resultsEl.style.display = 'none';
      overviewEl.style.display = 'block';
    });

    // "더 많은 결과" toggle for issue table
    $('#conIssuMoreBtn')?.addEventListener('click', (e) => {
      resultsEl.querySelectorAll('.con-issue-extra').forEach(r => r.style.display = '');
      e.target.remove();
    });

    // "더 보기" toggles for regulation groups
    resultsEl.querySelectorAll('[id^="conRegMore_"]').forEach(btn => {
      btn.addEventListener('click', () => {
        const group = btn.closest('.con-reg-group');
        group.querySelectorAll('.con-reg-extra').forEach(el => el.style.display = '');
        btn.remove();
      });
    });

  } catch (err) {
    resultsEl.innerHTML = `<div class="con-loading-state" style="color:var(--sem-error-t)">오류: ${esc(err.message)}</div>`;
  } finally {
    sendBtn.disabled = false;
  }
}

// Consistency textarea auto-resize
const conTextarea = $('#consistencyInput');
conTextarea.addEventListener('input', () => {
  conTextarea.style.height = 'auto';
  conTextarea.style.height = Math.min(conTextarea.scrollHeight, 100) + 'px';
});

conTextarea.addEventListener('keydown', (e) => {
  if (e.key === 'Enter' && (e.ctrlKey || e.metaKey)) {
    e.preventDefault();
    const val = conTextarea.value.trim();
    if (val) { runConsistencyCheck(val); conTextarea.value = ''; conTextarea.style.height = 'auto'; }
  }
});

$('#consistencySend').addEventListener('click', () => {
  const val = conTextarea.value.trim();
  if (val) { runConsistencyCheck(val); conTextarea.value = ''; conTextarea.style.height = 'auto'; }
});

// ── Sort order ───────────────────────────────────────────────
$('#sortSelect').addEventListener('change', (e) => {
  state.sortOrder = e.target.value;
  renderDocList();
});

// ══════════════════════════════════════════════════════════════
// View Navigation (sidebar + dashboard quick-access)
// ══════════════════════════════════════════════════════════════
state.currentView = 'dashboard';
const _viewLoaded = { dashboard: false, characters: false, world: false, timeline: false, graph: false, workspace: true };

function navigateTo(view) {
  if (!$('#view-' + view)) return;
  state.currentView = view;
  $$('.nav-item[data-view]').forEach(el => el.classList.toggle('active', el.dataset.view === view));
  $$('.view').forEach(el => el.classList.remove('active'));
  $('#view-' + view).classList.add('active');
  if (!_viewLoaded[view]) {
    _viewLoaded[view] = true;
    if (view === 'dashboard') loadDashboard();
    else if (view === 'characters') loadCharacters();
    else if (view === 'world') loadWorld();
    else if (view === 'timeline') loadTimeline();
    else if (view === 'graph') loadGraphView();
  }
}

$$('.nav-item[data-view]').forEach(btn => {
  btn.addEventListener('click', () => navigateTo(btn.dataset.view));
});
$$('.quick-card[data-view]').forEach(btn => {
  btn.addEventListener('click', () => navigateTo(btn.dataset.view));
});

// ── Dashboard ────────────────────────────────────────────────
async function loadDashboard() {
  try {
    const summary = await api('/narrative/summary');
    $('#statChars').textContent = summary.characters ?? 0;
    $('#statScenes').textContent = summary.scenes ?? 0;
    $('#statTimeline').textContent = summary.timeline_events ?? 0;
    $('#statLore').textContent = summary.lore_facts ?? 0;
    $('#statRel').textContent = summary.relationships ?? 0;
    $('#sbCharCount').textContent = summary.characters ?? 0;
    $('#sbSceneCount').textContent = summary.scenes ?? 0;
  } catch (_) { /* leave dashes */ }
  renderRecentDocs();
}

function renderRecentDocs() {
  const grid = $('#recentDocsGrid');
  if (!grid) return;
  if (!state.docs.length) {
    grid.innerHTML = `<div class="dash-empty">아직 업로드된 문서가 없습니다.</div>`;
    return;
  }
  const dbSources = ['characters_db', 'scenes_db'];
  const docs = state.docs.slice(0, 8);
  grid.innerHTML = docs.map(doc => {
    const typeClass = dbSources.includes(doc.source) ? 'type-db' : `type-${fileTypeClass(doc.name)}`;
    const label = dbSources.includes(doc.source) ? 'DB' : fileTypeLabel(doc.name);
    return `<div class="recent-doc-card" data-doc-id="${esc(doc.id)}">
      <div class="doc-file-icon ${typeClass}">${esc(label)}</div>
      <div class="recent-doc-name">${esc(doc.name)}</div>
      <div class="recent-doc-meta">${esc(doc.time_label)} · ${esc(doc.size_label)}</div>
    </div>`;
  }).join('');
  grid.querySelectorAll('[data-doc-id]').forEach(el => {
    el.addEventListener('click', () => {
      navigateTo('workspace');
      openDocInspector(el.dataset.docId);
    });
  });
}

// ── Characters ───────────────────────────────────────────────
const ROLE_LABELS = { protagonist: '주인공', antagonist: '적대자', supporting: '조연', extra: '단역' };
const ROLE_CLASSES = { protagonist: 'role-protagonist', antagonist: 'role-antagonist', supporting: 'role-supporting', extra: 'role-supporting' };
function roleLabel(role) { return ROLE_LABELS[role] || role || '인물'; }
function roleClass(role) { return ROLE_CLASSES[role] || 'role-supporting'; }

async function loadCharacters() {
  try {
    const chars = await api('/narrative/characters');
    state.characters = chars;
    renderCharacterList();
  } catch (e) {
    $('#charList').innerHTML = `<div class="doc-loading" style="color:var(--sem-error-t)">로드 실패: ${esc(e.message)}</div>`;
  }
}

function renderCharacterList() {
  const q = ($('#charSearchInput').value || '').trim().toLowerCase();
  let chars = state.characters || [];
  if (q) chars = chars.filter(c => (c.name || '').toLowerCase().includes(q));
  $('#charListCount').textContent = chars.length;

  const list = $('#charList');
  if (!chars.length) {
    list.innerHTML = `<div class="doc-loading" style="color:var(--t5)">인물이 없습니다.</div>`;
    return;
  }
  list.innerHTML = chars.map(c => {
    const isSel = state.selectedCharacterId === c.id;
    return `<div class="split-list-item ${isSel ? 'selected' : ''}" data-char-id="${esc(c.id)}">
      <div class="split-list-avatar">${esc((c.name || '?').slice(0, 1))}</div>
      <div class="split-list-info">
        <div class="split-list-name">${esc(c.name)}</div>
        <div class="split-list-meta">${esc(roleLabel(c.role))}</div>
      </div>
    </div>`;
  }).join('');
  list.querySelectorAll('[data-char-id]').forEach(el => {
    el.addEventListener('click', () => openCharacterDetail(el.dataset.charId));
  });
}

$('#charSearchInput').addEventListener('input', renderCharacterList);

async function openCharacterDetail(id) {
  state.selectedCharacterId = id;
  renderCharacterList();
  const panel = $('#charDetailPanel');
  panel.innerHTML = `<div class="doc-loading"><div class="spinner-sm"></div>불러오는 중...</div>`;

  const char = (state.characters || []).find(c => c.id === id);
  if (!char) return;

  let memory = { trait_events: [] };
  try { memory = await api(`/narrative/characters/${id}/memory`); } catch (_) { /* optional */ }

  const pbkd = char.pbkd || {};
  const pbkdLabels = { personality: '성격 (Personality)', beliefs: '신념 (Belief)', knowledge: '지식 (Knowledge)', desires: '욕망 (Desire)' };
  const pbkdHtml = Object.keys(pbkdLabels).map(key => {
    const items = pbkd[key] || [];
    return `<div class="pbkd-group">
      <div class="pbkd-group-title">${pbkdLabels[key]}</div>
      ${items.length
        ? `<div class="pbkd-tag-list">${items.map(t => `<span class="pbkd-tag">${esc(t)}</span>`).join('')}</div>`
        : `<div class="pbkd-empty">기록된 항목이 없습니다.</div>`}
    </div>`;
  }).join('');

  const events = memory.trait_events || [];
  const memoryHtml = events.length
    ? events.slice(0, 30).map(ev => `<div class="memory-event">
        <div class="memory-event-top">
          <span class="memory-trait">${esc(ev.trait || '')}</span>
          <span class="memory-confidence">${ev.confidence != null ? Math.round(ev.confidence * 100) + '%' : ''}</span>
        </div>
        ${ev.source_scene ? `<div class="memory-source">출처: ${esc(ev.source_scene)}</div>` : ''}
      </div>`).join('')
    : `<div class="rp-empty">기억 이벤트가 없습니다.</div>`;

  panel.innerHTML = `
    <div class="char-detail-header">
      <div class="char-detail-avatar">${esc((char.name || '?').slice(0, 1))}</div>
      <div>
        <div class="char-detail-name">${esc(char.name)}</div>
        <span class="char-role-badge ${roleClass(char.role)}">${esc(roleLabel(char.role))}</span>
      </div>
    </div>
    <div class="rp-tabs">
      <button class="rp-tab active" data-cdtab="info">기본 정보</button>
      <button class="rp-tab" data-cdtab="pbkd">PBKD</button>
      <button class="rp-tab" data-cdtab="memory">메모리</button>
    </div>
    <div class="rp-tab-content active" id="cdtab-info">
      <div class="rp-sections"><div class="rp-section">
        <div class="rp-field"><div class="rp-field-label">배경</div><div class="rp-field-value">${esc(char.background || '—')}</div></div>
        <div class="rp-field"><div class="rp-field-label">상태</div><div class="rp-field-value">${esc(char.status || '—')}</div></div>
        <div class="rp-field"><div class="rp-field-label">특성</div><div class="rp-field-value">${(char.traits || []).map(esc).join(', ') || '—'}</div></div>
        <div class="rp-field"><div class="rp-field-label">목표</div><div class="rp-field-value">${(char.goals || []).map(esc).join(', ') || '—'}</div></div>
      </div></div>
    </div>
    <div class="rp-tab-content" id="cdtab-pbkd"><div class="rp-sections">${pbkdHtml}</div></div>
    <div class="rp-tab-content" id="cdtab-memory"><div class="rp-sections">${memoryHtml}</div></div>
  `;

  panel.querySelectorAll('.rp-tab').forEach(tab => {
    tab.addEventListener('click', () => {
      panel.querySelectorAll('.rp-tab').forEach(t => t.classList.remove('active'));
      panel.querySelectorAll('.rp-tab-content').forEach(c => c.classList.remove('active'));
      tab.classList.add('active');
      panel.querySelector('#cdtab-' + tab.dataset.cdtab).classList.add('active');
    });
  });
}

// ── World & Lore ─────────────────────────────────────────────
async function loadWorld() {
  const grid = $('#loreGrid');
  try {
    const facts = await api('/narrative/world/lore');
    if (!facts.length) {
      grid.innerHTML = `<div class="view-empty-state">
        <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.2"><circle cx="12" cy="12" r="10"/><line x1="2" y1="12" x2="22" y2="12"/><path d="M12 2a15.3 15.3 0 010 20 15.3 15.3 0 010-20z"/></svg>
        <span>등록된 세계관 설정이 없습니다.</span>
      </div>`;
      return;
    }
    grid.innerHTML = facts.map(f => `<div class="lore-card">
      <div class="lore-key">${esc(f.key)}</div>
      <div class="lore-value">${esc(f.value)}</div>
      ${f.tags && f.tags.length ? `<div class="lore-tags">${f.tags.map(t => `<span class="lore-tag">${esc(t)}</span>`).join('')}</div>` : ''}
    </div>`).join('');
  } catch (e) {
    grid.innerHTML = `<div class="view-empty-state" style="color:var(--sem-error-t)">로드 실패: ${esc(e.message)}</div>`;
  }
}

// ── Timeline ─────────────────────────────────────────────────
async function loadTimeline() {
  const rail = $('#timelineRail');
  try {
    const events = await api('/narrative/timeline/events?kind=all');
    state.timelineEvents = events;
    $('#timelineSystemCount').textContent = events.filter(e => e.kind === 'system').length;
    renderTimeline();
  } catch (e) {
    rail.innerHTML = `<div class="view-empty-state" style="color:var(--sem-error-t);border:none;">로드 실패: ${esc(e.message)}</div>`;
  }
}

function renderTimeline() {
  const rail = $('#timelineRail');
  const showSystem = $('#timelineShowSystem').checked;
  const all = state.timelineEvents || [];
  const events = showSystem ? all : all.filter(e => e.kind !== 'system');

  if (!events.length) {
    rail.innerHTML = `<div class="view-empty-state" style="border:none;padding:30px 0;">등록된 연표 이벤트가 없습니다.</div>`;
    return;
  }
  const sorted = events.slice().sort((a, b) => new Date(a.happened_at) - new Date(b.happened_at));
  rail.innerHTML = sorted.map(ev => {
    const d = ev.happened_at ? new Date(ev.happened_at) : null;
    const dateLabel = d && !isNaN(d) ? d.toLocaleDateString('ko-KR', { year: 'numeric', month: '2-digit', day: '2-digit' }) : '';
    const isSystem = ev.kind === 'system';
    return `<div class="timeline-node${isSystem ? ' is-system' : ''}">
      <div class="timeline-dot"></div>
      ${dateLabel ? `<div class="timeline-date">${esc(dateLabel)}</div>` : ''}
      <div class="timeline-title-text">${esc(ev.title)}${isSystem ? '<span class="timeline-system-tag">시스템</span>' : ''}</div>
      ${ev.description ? `<div class="timeline-desc">${esc(ev.description)}</div>` : ''}
    </div>`;
  }).join('');
}

$('#timelineShowSystem').addEventListener('change', renderTimeline);

// ── Knowledge Graph ──────────────────────────────────────────
const NODE_TYPE_COLORS = {
  character: '#7C5FF5', trait: '#34D399', emotion: '#F472B6',
  concept: '#60A5FA', location: '#FBBF24', scene: '#A78BFA',
};
function nodeColor(type) { return NODE_TYPE_COLORS[type] || '#9199A6'; }

let graphAnimHandle = null;
const graphState = { currentCharId: null, currentCharName: null };

async function loadGraphView() {
  try {
    const chars = (state.characters && state.characters.length) ? state.characters : await api('/narrative/characters');
    state.characters = chars;
    const list = $('#graphCharList');
    list.innerHTML = chars.map(c => `<div class="split-list-item" data-char-id="${esc(c.id)}" data-char-name="${esc(c.name)}">
      <div class="split-list-avatar">${esc((c.name || '?').slice(0, 1))}</div>
      <div class="split-list-info">
        <div class="split-list-name">${esc(c.name)}</div>
        <div class="split-list-meta">${esc(roleLabel(c.role))}</div>
      </div>
    </div>`).join('');
    list.querySelectorAll('[data-char-id]').forEach(el => {
      el.addEventListener('click', () => selectGraphCharacter(el.dataset.charId, el.dataset.charName, list));
    });
  } catch (e) {
    $('#graphCharList').innerHTML = `<div class="doc-loading" style="color:var(--sem-error-t)">로드 실패: ${esc(e.message)}</div>`;
  }
}

$('#graphDepth').addEventListener('change', () => {
  if (graphState.currentCharId) {
    selectGraphCharacter(graphState.currentCharId, graphState.currentCharName, $('#graphCharList'));
  }
});

function _setGraphEmptyState(html) {
  const el = $('#graphEmpty');
  el.innerHTML = html;
  el.style.display = 'flex';
}

async function selectGraphCharacter(id, name, listEl) {
  graphState.currentCharId = id;
  graphState.currentCharName = name;
  listEl.querySelectorAll('.split-list-item').forEach(el => el.classList.toggle('selected', el.dataset.charId === id));
  $('#graphToolbarLabel').textContent = `${name}의 관계망을 불러오는 중...`;
  if (graphAnimHandle) { cancelAnimationFrame(graphAnimHandle); graphAnimHandle = null; }
  $('#graphLegend').innerHTML = '';
  _setGraphEmptyState(`<div class="spinner-sm"></div><p>관계망을 불러오는 중...</p>`);

  const depth = parseInt($('#graphDepth').value, 10) || 2;
  const nodeId = `character:${name.toLowerCase()}`;

  try {
    const [traverse, relSummary] = await Promise.all([
      api(`/narrative/knowledge-graph/traverse?node_id=${encodeURIComponent(nodeId)}&depth=${depth}`),
      api(`/narrative/relationships/graph/${id}`).catch(() => null),
    ]);
    if (graphState.currentCharId !== id) return; // a newer selection superseded this one
    renderGraphDetail(name, relSummary);
    $('#graphToolbarLabel').textContent = `${name}의 관계망을 표시 중`;
    if (!traverse.nodes || !traverse.nodes.length) {
      _setGraphEmptyState(`<p>${esc(name)}에 대한 그래프 데이터가 없습니다.</p>`);
      return;
    }
    $('#graphEmpty').style.display = 'none';
    initGraphCanvas(traverse.nodes, traverse.edges || [], nodeId);
  } catch (e) {
    if (graphState.currentCharId !== id) return;
    _setGraphEmptyState(`<p>관계 데이터를 불러오지 못했습니다.</p>`);
  }
}

function _resolveCharName(idOrName) {
  const found = (state.characters || []).find(c => c.id === idOrName);
  return found ? found.name : idOrName;
}

function renderGraphDetail(name, rel) {
  const panel = $('#graphDetailPanel');
  if (!rel) {
    panel.innerHTML = `<div class="split-detail-empty"><p>${esc(name)}에 대한<br>관계 정보가 없습니다.</p></div>`;
    return;
  }
  const field = (label, arr) => `<div class="rp-field">
    <div class="rp-field-label">${label}</div>
    <div class="rp-field-value">${arr && arr.length ? arr.map(_resolveCharName).map(esc).join(', ') : '—'}</div>
  </div>`;
  panel.innerHTML = `
    <div class="graph-detail-title">${esc(name)}</div>
    <div class="graph-detail-type">연결 ${rel.connections || 0}건</div>
    <div class="rp-sections"><div class="rp-section">
      ${field('동맹', rel.allies)}
      ${field('적대', rel.enemies)}
      ${field('로맨스', rel.romantic)}
    </div></div>
  `;
}

function initGraphCanvas(rawNodes, rawEdges, focusId) {
  const canvas = $('#graphCanvas');
  const ctx = canvas.getContext('2d');
  const rect = canvas.parentElement.getBoundingClientRect();
  const dpr = window.devicePixelRatio || 1;
  const W = rect.width, H = rect.height;
  canvas.width = W * dpr;
  canvas.height = H * dpr;
  canvas.style.width = W + 'px';
  canvas.style.height = H + 'px';
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);

  const MAX_NODES = 120;
  const limitedNodes = rawNodes.slice(0, MAX_NODES);
  const nodeById = {};
  const nodes = limitedNodes.map((n, i) => {
    const angle = (i / limitedNodes.length) * Math.PI * 2;
    const r = Math.min(W, H) * 0.3;
    return {
      id: n.node_id, type: n.node_type, label: n.label,
      x: W / 2 + Math.cos(angle) * r + (Math.random() - 0.5) * 20,
      y: H / 2 + Math.sin(angle) * r + (Math.random() - 0.5) * 20,
      vx: 0, vy: 0,
      isFocus: n.node_id === focusId,
    };
  });
  nodes.forEach(n => { nodeById[n.id] = n; });
  const edges = rawEdges
    .filter(e => nodeById[e.source] && nodeById[e.target])
    .map(e => ({ source: nodeById[e.source], target: nodeById[e.target], type: e.edge_type }));

  const typesPresent = [...new Set(nodes.map(n => n.type))];
  $('#graphLegend').innerHTML = typesPresent.map(t =>
    `<div class="graph-legend-item"><span class="graph-legend-dot" style="background:${nodeColor(t)}"></span>${esc(t)}</div>`
  ).join('');

  if (graphAnimHandle) cancelAnimationFrame(graphAnimHandle);

  let dragging = null;
  let hovered = null;

  function tick() {
    for (let i = 0; i < nodes.length; i++) {
      for (let j = i + 1; j < nodes.length; j++) {
        const a = nodes[i], b = nodes[j];
        const dx = a.x - b.x, dy = a.y - b.y;
        const distSq = dx * dx + dy * dy || 0.01;
        const dist = Math.sqrt(distSq);
        const minDist = 60;
        if (dist < minDist * 3) {
          const force = (minDist * minDist) / distSq * 0.6;
          const fx = (dx / dist) * force, fy = (dy / dist) * force;
          a.vx += fx; a.vy += fy;
          b.vx -= fx; b.vy -= fy;
        }
      }
    }
    edges.forEach(e => {
      const dx = e.target.x - e.source.x, dy = e.target.y - e.source.y;
      const dist = Math.sqrt(dx * dx + dy * dy) || 0.01;
      const targetLen = 85;
      const force = (dist - targetLen) * 0.02;
      const fx = (dx / dist) * force, fy = (dy / dist) * force;
      e.source.vx += fx; e.source.vy += fy;
      e.target.vx -= fx; e.target.vy -= fy;
    });
    nodes.forEach(n => {
      if (n === dragging) return;
      n.vx += (W / 2 - n.x) * 0.0025;
      n.vy += (H / 2 - n.y) * 0.0025;
      n.vx *= 0.82; n.vy *= 0.82;
      n.x += n.vx; n.y += n.vy;
      n.x = Math.max(20, Math.min(W - 20, n.x));
      n.y = Math.max(20, Math.min(H - 20, n.y));
    });

    ctx.clearRect(0, 0, W, H);
    ctx.strokeStyle = 'rgba(255,255,255,0.14)';
    ctx.lineWidth = 1;
    edges.forEach(e => {
      ctx.beginPath();
      ctx.moveTo(e.source.x, e.source.y);
      ctx.lineTo(e.target.x, e.target.y);
      ctx.stroke();
    });
    nodes.forEach(n => {
      const r = n.isFocus ? 10 : 6;
      ctx.beginPath();
      ctx.arc(n.x, n.y, r, 0, Math.PI * 2);
      ctx.fillStyle = nodeColor(n.type);
      ctx.fill();
      if (n.isFocus || n === hovered) {
        ctx.lineWidth = 2;
        ctx.strokeStyle = '#fff';
        ctx.stroke();
      }
      ctx.fillStyle = '#E7E9EF';
      ctx.font = '11px -apple-system, sans-serif';
      ctx.fillText(n.label, n.x + r + 4, n.y + 4);
    });

    graphAnimHandle = requestAnimationFrame(tick);
  }
  tick();

  function nodeAt(x, y) {
    return nodes.find(n => Math.hypot(n.x - x, n.y - y) < 12);
  }
  function toLocal(evt) {
    const b = canvas.getBoundingClientRect();
    return { x: evt.clientX - b.left, y: evt.clientY - b.top };
  }
  canvas.onmousedown = (evt) => {
    const p = toLocal(evt);
    const n = nodeAt(p.x, p.y);
    if (n) dragging = n;
  };
  canvas.onmousemove = (evt) => {
    const p = toLocal(evt);
    if (dragging) { dragging.x = p.x; dragging.y = p.y; dragging.vx = 0; dragging.vy = 0; }
    else hovered = nodeAt(p.x, p.y);
  };
  window.addEventListener('mouseup', () => { dragging = null; });
  canvas.onclick = (evt) => {
    const p = toLocal(evt);
    const n = nodeAt(p.x, p.y);
    if (n) renderGraphNodeDetail(n);
  };
}

function renderGraphNodeDetail(node) {
  const panel = $('#graphDetailPanel');
  panel.innerHTML = `
    <div class="graph-detail-title">${esc(node.label)}</div>
    <div class="graph-detail-type">유형: ${esc(node.type)}</div>
  `;
}

// ── Init ─────────────────────────────────────────────────────
loadDocuments();
loadDashboard();
