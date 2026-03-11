/**
 * Moonstone Workspace — Tiling Window Manager
 * Recursive binary tree layout with drag-resize splitters.
 */

/* ============================================================
   Globals
   ============================================================ */
let _applets = [];       // from /api/applets
let _root = null;        // layout tree root node
let _activeLayout = '';  // current layout name
let _layouts = {};       // saved layouts { name: treeJSON }
let _idCounter = 0;
const STORE_KEY = 'workspace';
const MIN_PANEL_PX = 150;

/* ============================================================
   Layout Tree Node
   type: 'split' | 'leaf'
   ============================================================ */
function makeLeaf(applet) {
  return { type: 'leaf', id: 'p' + (++_idCounter), applet: applet || null };
}

function makeSplit(dir, ratio, a, b) {
  return { type: 'split', id: 's' + (++_idCounter), direction: dir, ratio: ratio, children: [a, b] };
}

function cloneTree(node) {
  return JSON.parse(JSON.stringify(node));
}

/* ============================================================
   Presets
   ============================================================ */
const PRESETS = {
  'Single': function() { return makeLeaf(null); },
  'Side by Side': function() { return makeSplit('horizontal', 0.5, makeLeaf(null), makeLeaf(null)); },
  'Top / Bottom': function() { return makeSplit('vertical', 0.5, makeLeaf(null), makeLeaf(null)); },
  'Project View': function() {
    return makeSplit('vertical', 0.5,
      makeSplit('horizontal', 0.6, makeLeaf(null), makeLeaf(null)),
      makeLeaf(null)
    );
  },
  '2\u00d72 Grid': function() {
    return makeSplit('vertical', 0.5,
      makeSplit('horizontal', 0.5, makeLeaf(null), makeLeaf(null)),
      makeSplit('horizontal', 0.5, makeLeaf(null), makeLeaf(null))
    );
  },
};

/* ============================================================
   Init
   ============================================================ */
async function init() {
  try {
    var resp = await fetch('/api/applets');
    var data = await resp.json();
    _applets = data.applets || [];
  } catch(e) { _applets = []; }
  await loadLayouts();
  renderToolbar();
  renderLayout();
}

/* ============================================================
   Persistence (KV Store)
   ============================================================ */
async function loadLayouts() {
  try {
    var resp = await fetch('/api/store/' + STORE_KEY + '/layouts');
    var data = await resp.json();
    if (data.value) _layouts = data.value;
  } catch(e) { _layouts = {}; }
  try {
    var resp2 = await fetch('/api/store/' + STORE_KEY + '/active');
    var data2 = await resp2.json();
    if (data2.value) _activeLayout = data2.value;
  } catch(e) {}
  try {
    var resp3 = await fetch('/api/store/' + STORE_KEY + '/last-state');
    var data3 = await resp3.json();
    if (data3.value) { _root = data3.value; return; }
  } catch(e) {}
  _root = PRESETS['Single']();
}

function saveState() {
  var body = JSON.stringify({ value: _root });
  fetch('/api/store/' + STORE_KEY + '/last-state', {
    method: 'PUT', headers: {'Content-Type':'application/json'}, body: body
  }).catch(function(){});
}

var _saveDebounce = null;
function debouncedSave() {
  if (_saveDebounce) clearTimeout(_saveDebounce);
  _saveDebounce = setTimeout(saveState, 800);
}

async function saveLayoutAs(name) {
  _layouts[name] = cloneTree(_root);
  _activeLayout = name;
  await fetch('/api/store/' + STORE_KEY + '/layouts', {
    method: 'PUT', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ value: _layouts })
  });
  await fetch('/api/store/' + STORE_KEY + '/active', {
    method: 'PUT', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ value: _activeLayout })
  });
  toast('Layout "' + name + '" saved');
  renderToolbar();
}

async function loadLayout(name) {
  if (!_layouts[name]) return;
  _root = cloneTree(_layouts[name]);
  _activeLayout = name;
  await fetch('/api/store/' + STORE_KEY + '/active', {
    method: 'PUT', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ value: _activeLayout })
  });
  renderLayout();
  debouncedSave();
  toast('Loaded "' + name + '"');
}

async function deleteLayout(name) {
  delete _layouts[name];
  if (_activeLayout === name) _activeLayout = '';
  await fetch('/api/store/' + STORE_KEY + '/layouts', {
    method: 'PUT', headers: {'Content-Type':'application/json'},
    body: JSON.stringify({ value: _layouts })
  });
  renderToolbar();
  toast('Deleted "' + name + '"');
}

/* ============================================================
   Tree operations
   ============================================================ */
function findParent(root, nodeId) {
  if (!root || root.type !== 'split') return null;
  for (var i = 0; i < 2; i++) {
    if (root.children[i].id === nodeId) return { parent: root, index: i };
    if (root.children[i].type === 'split') {
      var r = findParent(root.children[i], nodeId);
      if (r) return r;
    }
  }
  return null;
}

function splitPanel(nodeId, direction) {
  if (_root.id === nodeId && _root.type === 'leaf') {
    var oldLeaf = cloneTree(_root);
    _root = makeSplit(direction, 0.5, oldLeaf, makeLeaf(null));
  } else {
    var info = findParent(_root, nodeId);
    if (!info) return;
    var oldNode = info.parent.children[info.index];
    info.parent.children[info.index] = makeSplit(direction, 0.5, cloneTree(oldNode), makeLeaf(null));
  }
  renderLayout();
  debouncedSave();
}

function closePanel(nodeId) {
  if (_root.id === nodeId) {
    _root = makeLeaf(null);
    renderLayout();
    debouncedSave();
    return;
  }
  var info = findParent(_root, nodeId);
  if (!info) return;
  var siblingIdx = info.index === 0 ? 1 : 0;
  var sibling = info.parent.children[siblingIdx];
  var grandInfo = findParent(_root, info.parent.id);
  if (!grandInfo) {
    _root = sibling;
  } else {
    grandInfo.parent.children[grandInfo.index] = sibling;
  }
  renderLayout();
  debouncedSave();
}

function setApplet(nodeId, appletName) {
  var node = findNodeById(_root, nodeId);
  if (node && node.type === 'leaf') {
    node.applet = appletName;
    renderLayout();
    debouncedSave();
  }
}

function findNodeById(root, nodeId) {
  if (!root) return null;
  if (root.id === nodeId) return root;
  if (root.type === 'split') {
    return findNodeById(root.children[0], nodeId) || findNodeById(root.children[1], nodeId);
  }
  return null;
}

function countLeaves(node) {
  if (!node) return 0;
  if (node.type === 'leaf') return 1;
  return countLeaves(node.children[0]) + countLeaves(node.children[1]);
}

/* ============================================================
   Render layout tree → DOM (PLACEHOLDER - filled in next step)
   ============================================================ */
function renderLayout() {
  var main = document.getElementById('wsMain');
  main.innerHTML = '';
  if (!_root) { _root = makeLeaf(null); }
  main.appendChild(renderNode(_root));
  updateStatus();
}

function renderNode(node) {
  if (node.type === 'leaf') return renderLeaf(node);
  return renderSplit(node);
}

function renderSplit(node) {
  var el = document.createElement('div');
  el.className = 'ws-split ws-split-' + (node.direction === 'horizontal' ? 'h' : 'v');
  el.dataset.id = node.id;
  var pct1 = (node.ratio * 100).toFixed(2);
  var pct2 = (100 - node.ratio * 100).toFixed(2);
  var splitter = 'var(--ws-splitter)';
  if (node.direction === 'horizontal') {
    el.style.gridTemplateColumns = pct1 + '% ' + splitter + ' ' + pct2 + '%';
  } else {
    el.style.gridTemplateRows = pct1 + '% ' + splitter + ' ' + pct2 + '%';
  }
  el.appendChild(renderNode(node.children[0]));
  var handle = document.createElement('div');
  handle.className = 'ws-splitter';
  handle.dataset.splitId = node.id;
  handle.addEventListener('mousedown', onSplitterDown);
  el.appendChild(handle);
  el.appendChild(renderNode(node.children[1]));
  return el;
}

function renderLeaf(node) {
  var panel = document.createElement('div');
  panel.className = 'ws-panel ws-panel-enter';
  panel.dataset.id = node.id;
  var appInfo = node.applet ? getAppletInfo(node.applet) : null;
  // Header
  var hdr = document.createElement('div');
  hdr.className = 'ws-panel-header';
  var icon = document.createElement('span');
  icon.className = 'ws-panel-icon';
  icon.textContent = appInfo ? (appInfo.icon || '\u{1F4E6}') : '\u{1F4CB}';
  hdr.appendChild(icon);
  var title = document.createElement('span');
  title.className = 'ws-panel-title';
  title.textContent = appInfo ? appInfo.label : 'Select applet';
  title.style.cursor = 'pointer';
  title.addEventListener('click', function(e) { e.stopPropagation(); showAppletChooser(node.id, panel); });
  hdr.appendChild(title);
  // Actions
  var acts = document.createElement('div');
  acts.className = 'ws-panel-actions';
  acts.appendChild(makeBtn('\u2194', 'Split Right', function() { splitPanel(node.id, 'horizontal'); }));
  acts.appendChild(makeBtn('\u2195', 'Split Down', function() { splitPanel(node.id, 'vertical'); }));
  acts.appendChild(makeBtn('\u25A1', 'Change applet', function(e) { e.stopPropagation(); showAppletChooser(node.id, panel); }));
  var closeB = makeBtn('\u2715', 'Close', function() { closePanel(node.id); });
  closeB.classList.add('close-btn');
  acts.appendChild(closeB);
  hdr.appendChild(acts);
  panel.appendChild(hdr);
  // Body
  var body = document.createElement('div');
  body.className = 'ws-panel-body';
  if (node.applet) {
    var iframe = document.createElement('iframe');
    iframe.src = '/apps/' + node.applet + '/';
    iframe.setAttribute('loading', 'lazy');
    iframe.setAttribute('sandbox', 'allow-scripts allow-same-origin allow-popups allow-forms');
    body.appendChild(iframe);
  } else {
    body.appendChild(renderEmptyPanel(node.id));
  }
  panel.appendChild(body);
  return panel;
}

function makeBtn(text, tooltip, handler) {
  var b = document.createElement('button');
  b.className = 'ws-panel-btn';
  b.title = tooltip;
  b.textContent = text;
  b.addEventListener('click', handler);
  return b;
}

function renderEmptyPanel(nodeId) {
  var wrap = document.createElement('div');
  wrap.className = 'ws-empty-panel';
  var ic = document.createElement('div');
  ic.className = 'ws-empty-icon';
  ic.textContent = '\u{1F9E9}';
  wrap.appendChild(ic);
  var txt = document.createElement('div');
  txt.className = 'ws-empty-text';
  txt.textContent = 'Choose an applet for this panel';
  wrap.appendChild(txt);
  // Search input for grid
  var search = document.createElement('input');
  search.className = 'ws-applet-chooser-search';
  search.type = 'text';
  search.placeholder = 'Search applets\u2026';
  search.style.maxWidth = '480px';
  search.style.marginBottom = '8px';
  wrap.appendChild(search);
  var grid = document.createElement('div');
  grid.className = 'ws-applet-grid';
  function renderCards(query) {
    grid.innerHTML = '';
    var q = (query || '').toLowerCase();
    _applets.forEach(function(a) {
      if (q && (a.label || '').toLowerCase().indexOf(q) === -1 && (a.name || '').toLowerCase().indexOf(q) === -1) return;
      var card = document.createElement('div');
      card.className = 'ws-applet-card';
      card.addEventListener('click', function() { setApplet(nodeId, a.name); });
      var ci = document.createElement('div');
      ci.className = 'ws-applet-card-icon';
      ci.textContent = a.icon || '\u{1F4E6}';
      card.appendChild(ci);
      var cn = document.createElement('div');
      cn.className = 'ws-applet-card-name';
      cn.textContent = a.label;
      card.appendChild(cn);
      grid.appendChild(card);
    });
  }
  renderCards('');
  search.addEventListener('input', function() { renderCards(search.value); });
  wrap.appendChild(grid);
  return wrap;
}

function getAppletInfo(name) {
  for (var i = 0; i < _applets.length; i++) {
    if (_applets[i].name === name) return _applets[i];
  }
  return { name: name, label: name, icon: '\u{1F4E6}' };
}

/* ============================================================
   Applet chooser dropdown
   ============================================================ */
function showAppletChooser(nodeId, panelEl) {
  closeAllPopups();
  var chooser = document.createElement('div');
  chooser.className = 'ws-applet-chooser';
  chooser.id = 'activeChooser';
  // Search input
  var search = document.createElement('input');
  search.className = 'ws-applet-chooser-search';
  search.type = 'text';
  search.placeholder = 'Search applets\u2026';
  search.addEventListener('click', function(e) { e.stopPropagation(); });
  chooser.appendChild(search);
  // Items container
  var itemsWrap = document.createElement('div');
  function renderItems(query) {
    itemsWrap.innerHTML = '';
    var q = (query || '').toLowerCase();
    _applets.forEach(function(a) {
      if (q && (a.label || '').toLowerCase().indexOf(q) === -1 && (a.name || '').toLowerCase().indexOf(q) === -1) return;
      var item = document.createElement('div');
      item.className = 'ws-applet-chooser-item';
      item.innerHTML = '<span class="icon">' + esc(a.icon || '\u{1F4E6}') + '</span>' +
        '<span class="name">' + esc(a.label) + '</span>';
      item.addEventListener('click', function(e) {
        e.stopPropagation();
        setApplet(nodeId, a.name);
        closeAllPopups();
      });
      itemsWrap.appendChild(item);
    });
  }
  renderItems('');
  search.addEventListener('input', function() { renderItems(search.value); });
  chooser.appendChild(itemsWrap);
  panelEl.style.position = 'relative';
  panelEl.appendChild(chooser);
  setTimeout(function() { search.focus(); }, 20);
  setTimeout(function() { document.addEventListener('click', closeAllPopups, { once: true }); }, 10);
}

function closeAllPopups() {
  var el = document.getElementById('activeChooser');
  if (el) el.remove();
  var dd = document.querySelector('.ws-layout-dropdown.open');
  if (dd) dd.classList.remove('open');
}

/* ============================================================
   Splitter drag
   ============================================================ */
var _dragging = null;

function onSplitterDown(e) {
  e.preventDefault();
  var splitId = e.target.dataset.splitId;
  var node = findNodeById(_root, splitId);
  if (!node || node.type !== 'split') return;
  var splitEl = e.target.parentElement;
  var rect = splitEl.getBoundingClientRect();
  _dragging = { node: node, rect: rect, dir: node.direction };
  e.target.classList.add('active');
  var overlay = document.getElementById('dragOverlay');
  overlay.classList.add('active');
  overlay.style.cursor = node.direction === 'horizontal' ? 'col-resize' : 'row-resize';
  document.addEventListener('mousemove', onSplitterMove);
  document.addEventListener('mouseup', onSplitterUp);
}

function onSplitterMove(e) {
  if (!_dragging) return;
  var r = _dragging.rect;
  var ratio;
  if (_dragging.dir === 'horizontal') {
    ratio = (e.clientX - r.left) / r.width;
  } else {
    ratio = (e.clientY - r.top) / r.height;
  }
  var minR = MIN_PANEL_PX / (_dragging.dir === 'horizontal' ? r.width : r.height);
  ratio = Math.max(minR, Math.min(1 - minR, ratio));
  _dragging.node.ratio = ratio;
  // Update grid template directly (no full re-render for smoothness)
  var splitEl = document.querySelector('[data-id="' + _dragging.node.id + '"]');
  if (splitEl) {
    var pct1 = (ratio * 100).toFixed(2);
    var pct2 = (100 - ratio * 100).toFixed(2);
    var s = 'var(--ws-splitter)';
    if (_dragging.dir === 'horizontal') {
      splitEl.style.gridTemplateColumns = pct1 + '% ' + s + ' ' + pct2 + '%';
    } else {
      splitEl.style.gridTemplateRows = pct1 + '% ' + s + ' ' + pct2 + '%';
    }
  }
}

function onSplitterUp(e) {
  document.removeEventListener('mousemove', onSplitterMove);
  document.removeEventListener('mouseup', onSplitterUp);
  document.getElementById('dragOverlay').classList.remove('active');
  var active = document.querySelector('.ws-splitter.active');
  if (active) active.classList.remove('active');
  _dragging = null;
  debouncedSave();
}

/* ============================================================
   Toolbar rendering
   ============================================================ */
function renderToolbar() {
  // Update layout dropdown
  var dd = document.getElementById('layoutDropdown');
  if (!dd) return;
  dd.innerHTML = '';
  // Presets section
  var hdr1 = document.createElement('div');
  hdr1.className = 'ws-layout-dropdown-header';
  hdr1.textContent = 'Presets';
  dd.appendChild(hdr1);
  Object.keys(PRESETS).forEach(function(name) {
    dd.appendChild(makeLayoutItem(name, true));
  });
  // Saved layouts
  var savedNames = Object.keys(_layouts);
  if (savedNames.length) {
    var divider = document.createElement('div');
    divider.className = 'ws-layout-dropdown-divider';
    dd.appendChild(divider);
    var hdr2 = document.createElement('div');
    hdr2.className = 'ws-layout-dropdown-header';
    hdr2.textContent = 'Saved';
    dd.appendChild(hdr2);
    savedNames.forEach(function(name) {
      dd.appendChild(makeLayoutItem(name, false));
    });
  }
  // Update current label
  var cur = document.getElementById('layoutCurrentLabel');
  if (cur) cur.textContent = _activeLayout || 'Untitled';
}

function makeLayoutItem(name, isPreset) {
  var item = document.createElement('div');
  item.className = 'ws-layout-item' + (_activeLayout === name ? ' active' : '');
  var nm = document.createElement('span');
  nm.className = 'name';
  nm.textContent = name;
  item.appendChild(nm);
  if (!isPreset) {
    var del = document.createElement('button');
    del.className = 'delete-btn';
    del.textContent = '\u2715';
    del.title = 'Delete';
    del.addEventListener('click', function(e) { e.stopPropagation(); deleteLayout(name); });
    item.appendChild(del);
  }
  item.addEventListener('click', function() {
    closeAllPopups();
    if (isPreset) {
      _root = PRESETS[name]();
      _activeLayout = '';
      renderLayout();
      debouncedSave();
    } else {
      loadLayout(name);
    }
  });
  return item;
}

function toggleLayoutDropdown() {
  closeAllPopups();
  var dd = document.getElementById('layoutDropdown');
  dd.classList.toggle('open');
  if (dd.classList.contains('open')) {
    renderToolbar();
    setTimeout(function() {
      document.addEventListener('click', function handler(e) {
        if (!dd.contains(e.target)) { dd.classList.remove('open'); }
        document.removeEventListener('click', handler);
      });
    }, 10);
  }
}

/* ============================================================
   Save dialog
   ============================================================ */
function openSaveDialog() {
  var overlay = document.getElementById('saveOverlay');
  overlay.classList.add('open');
  var input = document.getElementById('saveNameInput');
  input.value = _activeLayout || '';
  input.focus();
  input.select();
}

function closeSaveDialog() {
  document.getElementById('saveOverlay').classList.remove('open');
}

function doSave() {
  var name = document.getElementById('saveNameInput').value.trim();
  if (!name) return;
  saveLayoutAs(name);
  closeSaveDialog();
}

/* ============================================================
   Status bar
   ============================================================ */
function updateStatus() {
  var el = document.getElementById('statusInfo');
  if (el) el.textContent = countLeaves(_root) + ' panels';
}

/* ============================================================
   Toast
   ============================================================ */
function toast(msg) {
  var old = document.querySelector('.ws-toast');
  if (old) old.remove();
  var t = document.createElement('div');
  t.className = 'ws-toast';
  t.textContent = msg;
  document.body.appendChild(t);
  setTimeout(function() { t.remove(); }, 2500);
}

/* ============================================================
   Helpers
   ============================================================ */
function esc(s) {
  var d = document.createElement('span');
  d.textContent = s;
  return d.innerHTML;
}

/* ============================================================
   Keyboard shortcuts
   ============================================================ */
document.addEventListener('keydown', function(e) {
  if (e.key === 'Escape') closeAllPopups();
  if (e.key === 's' && (e.ctrlKey || e.metaKey)) { e.preventDefault(); openSaveDialog(); }
});

/* ============================================================
   Boot
   ============================================================ */
document.addEventListener('DOMContentLoaded', init);
