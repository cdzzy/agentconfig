// AgentConfig — shared JS utilities

// ── Toast ──────────────────────────────────────────────────────────────────
const toastWrap = (() => {
  const el = document.createElement('div');
  el.className = 'toast-wrap';
  document.body.appendChild(el);
  return el;
})();

function toast(msg, type = 'info', ms = 3000) {
  const t = document.createElement('div');
  t.className = `toast toast-${type === 'ok' ? 'ok' : type === 'err' ? 'err' : 'info'}`;
  t.textContent = msg;
  toastWrap.appendChild(t);
  setTimeout(() => t.remove(), ms);
}

// ── API helper ─────────────────────────────────────────────────────────────
async function api(method, url, body) {
  const opts = { method, headers: { 'Content-Type': 'application/json' } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const res  = await fetch(url, opts);
  const data = await res.json();
  if (!res.ok) throw new Error(data.error || res.statusText);
  return data;
}

// ── Tags input ─────────────────────────────────────────────────────────────
function initTagsInput(wrap, onChange) {
  const inp = wrap.querySelector('input');
  let tags  = [];

  function render() {
    wrap.querySelectorAll('.tag').forEach(t => t.remove());
    tags.forEach((tag, i) => {
      const el = document.createElement('span');
      el.className = 'tag';
      el.innerHTML = `${esc(tag)}<span class="tag-rm" data-i="${i}">×</span>`;
      wrap.insertBefore(el, inp);
    });
    onChange && onChange(tags);
  }

  wrap.addEventListener('click', () => inp.focus());
  wrap.addEventListener('focusin',  () => wrap.classList.add('focused'));
  wrap.addEventListener('focusout', () => wrap.classList.remove('focused'));

  inp.addEventListener('keydown', e => {
    if ((e.key === 'Enter' || e.key === ',') && inp.value.trim()) {
      e.preventDefault();
      const v = inp.value.trim().replace(/,$/, '');
      if (v && !tags.includes(v)) { tags.push(v); render(); }
      inp.value = '';
    }
    if (e.key === 'Backspace' && !inp.value && tags.length) {
      tags.pop(); render();
    }
  });

  wrap.addEventListener('click', e => {
    if (e.target.classList.contains('tag-rm')) {
      tags.splice(+e.target.dataset.i, 1);
      render();
    }
  });

  return {
    get: () => [...tags],
    set: (arr) => { tags = [...(arr || [])]; render(); },
    clear: () => { tags = []; render(); },
  };
}

// ── Misc ───────────────────────────────────────────────────────────────────
function esc(s) {
  return String(s)
    .replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;')
    .replace(/"/g,'&quot;');
}

function fmtDate(iso) {
  if (!iso) return '—';
  const d = new Date(iso);
  return d.toLocaleDateString() + ' ' + d.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
}

function fmtMs(ms) {
  if (!ms) return '—';
  return ms < 1000 ? `${Math.round(ms)}ms` : `${(ms/1000).toFixed(1)}s`;
}

function statusBadge(status) {
  const map = {
    completed: ['badge-ok',   'Completed'],
    running:   ['badge-blue', 'Running'],
    escalated: ['badge-warn', 'Escalated'],
    error:     ['badge-err',  'Error'],
    blocked:   ['badge-err',  'Blocked'],
    timeout:   ['badge-err',  'Timeout'],
  };
  const [cls, label] = map[status] || ['badge-muted', status];
  return `<span class="badge ${cls}">${label}</span>`;
}

function domainBadge(domain) {
  const labels = {
    customer_service: 'Customer Service',
    sales:            'Sales',
    hr:               'HR',
    finance:          'Finance',
    it_support:       'IT Support',
    legal:            'Legal',
    marketing:        'Marketing',
    general:          'General',
  };
  return `<span class="badge badge-teal">${labels[domain] || domain}</span>`;
}

// Highlight active nav link
document.querySelectorAll('nav a').forEach(a => {
  if (a.getAttribute('href') === location.pathname) a.classList.add('active');
});
