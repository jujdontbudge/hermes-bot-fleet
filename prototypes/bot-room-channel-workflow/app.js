/* THROWAWAY issue #8 interaction prototype. Not production fleet code. */
(() => {
  'use strict';
  const $ = (selector, root = document) => root.querySelector(selector);
  const $$ = (selector, root = document) => [...root.querySelectorAll(selector)];
  const allowedVariants = ['guided', 'canvas', 'console'];
  const requestedVariant = new URLSearchParams(location.search).get('variant');
  const variant = allowedVariants.includes(requestedVariant) ? requestedVariant : 'guided';
  document.body.classList.add(`variant-${variant}`);
  $$('[data-variant]').forEach(a => a.classList.toggle('active', a.dataset.variant === variant));

  const state = {
    variant, view: 'create', selectedBot: 'chief', macOnline: false,
    bots: {
      chief: { title: 'Coordinator', runtime: 'server', browser: 'AUTOMATION', online: true },
      'test-worker': { title: 'Safe tester', runtime: 'server', browser: 'RECOVERING', online: true },
      'laptop-worker': { title: 'Mac operator', runtime: 'mac', browser: 'NONE', online: false }
    },
    room: ['chief', 'test-worker'], channel: null,
    routines: { 'Daily fleet brief': 'success', 'Acceptance smoke': 'failed', 'Agent Inbox review': 'paused offline' },
    activity: ['Prototype state loaded']
  };
  window.prototypeState = state;

  function escapeHtml(value) {
    return String(value).replace(/[&<>'"]/g, c => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', "'": '&#39;', '"': '&quot;' }[c]));
  }
  function toast(message) {
    const node = $('#toast'); node.textContent = message; node.classList.add('show');
    clearTimeout(toast.timer); toast.timer = setTimeout(() => node.classList.remove('show'), 1800);
  }
  function activity(message) {
    state.activity.unshift(message); state.activity = state.activity.slice(0, 8); renderState();
  }
  function stateMarkup() {
    const bot = state.bots[state.selectedBot];
    return `<dl><dt>Variant</dt><dd>${escapeHtml(state.variant)}</dd><dt>View</dt><dd>${escapeHtml(state.view)}</dd><dt>Selected Bot</dt><dd>${escapeHtml(state.selectedBot)}</dd><dt>Runtime</dt><dd>${escapeHtml(bot.runtime)}</dd><dt>Browser</dt><dd>${escapeHtml(bot.browser)}</dd><dt>Room members</dt><dd>${state.room.map(escapeHtml).join(', ')}</dd><dt>Mac</dt><dd>${state.macOnline ? 'connected' : 'unavailable'}</dd><dt>Channel</dt><dd>${state.channel ? escapeHtml(`${state.channel.label} → ${state.channel.bot}`) : 'not mapped'}</dd></dl>`;
  }
  function renderState() {
    $('#liveState').innerHTML = stateMarkup();
    $('#activityLog').innerHTML = state.activity.map((item, i) => `<li><time>${i ? 'earlier' : 'now'}</time> ${escapeHtml(item)}</li>`).join('');
    $('#botCount').textContent = Object.keys(state.bots).length;
    $('#roomRosterMeta').textContent = `${state.room.length} bots · ready`;
  }
  function openView(name) {
    if (!$('#view-' + name)) return;
    state.view = name;
    $$('.view').forEach(v => v.classList.toggle('active', v.id === `view-${name}`));
    $$('[data-view]').forEach(b => b.toggleAttribute('aria-current', b.dataset.view === name));
    renderState();
  }
  $$('[data-view]').forEach(button => button.addEventListener('click', () => openView(button.dataset.view)));

  function selectBot(name) {
    if (!state.bots[name]) return;
    state.selectedBot = name;
    $$('.bot-row').forEach(row => row.classList.toggle('selected', row.dataset.bot === name));
    const bot = state.bots[name];
    $('#chat-title').innerHTML = `${escapeHtml(name)} <small>on ${bot.runtime === 'mac' ? 'johan-mac' : 'fleet-server'}</small>`;
    openView('chat'); activity(`Opened ${name} canonical Bot Chat`);
  }
  $$('.bot-row').forEach(row => row.addEventListener('click', () => selectBot(row.dataset.bot)));

  const runtimeInputs = $$('input[name=runtime]');
  function updateImplications() {
    const runtime = $('input[name=runtime]:checked').value;
    const browser = $('#browserProfile').value;
    const mac = runtime === 'mac';
    $('#implications').innerHTML = `<ul><li><b>${mac ? 'Mac Laptop Runtime' : 'Server Runtime'}:</b> ${mac ? 'intermittent; offline work pauses and every mutation requires a Mac-local, single-use approval.' : 'always-on; separate Unix identity and Bot-scoped containers, not merely a Hermes profile.'}</li><li><b>Browser:</b> ${browser === 'none' ? 'no browser authority is granted.' : `${mac ? 'Mac-owned browser; no server Browser Profile is created.' : 'dedicated persistent profile; starts RECOVERING and must pass a harmless probe.'}`}</li><li><b>Credentials:</b> handles are broker references; messages, Rooms, and delegation never increase authority.</li></ul>`;
    $('#browserHint').textContent = mac ? 'Mac-owned browser state; unavailable while the laptop is offline.' : 'Bot-scoped profile; never cloned or shared. Starts in RECOVERING.';
  }
  runtimeInputs.forEach(input => input.addEventListener('change', updateImplications));
  $('#browserProfile').addEventListener('change', updateImplications);
  updateImplications();

  function validationErrors() {
    const name = $('#botName').value.trim();
    const errors = [];
    if (!/^[a-z][a-z0-9-]{2,31}$/.test(name)) errors.push('Profile name must be 3–32 lowercase letters, numbers, or hyphens and start with a letter.');
    if (state.bots[name]) errors.push('That Bot/profile name already exists.');
    if (!$('#botTitle').value.trim()) errors.push('Operator title is required.');
    if (!$('#botDescription').value.trim()) errors.push('Role / description is required.');
    if (!$('#persona').value.trim()) errors.push('Persona is required.');
    if (!/^secret:\/\/[a-z0-9-]+\/[a-z0-9/_-]+$/i.test($('#credential').value.trim())) errors.push('Credential must be an opaque secret:// handle, never a token value.');
    if (!$('#reviewConfirm').checked) errors.push('Review and confirm runtime, isolation, credentials, and approval implications.');
    return errors;
  }
  function showValidation(errors) {
    const review = $('.review');
    let box = $('#validationResult');
    if (!box) { box = document.createElement('div'); box.id = 'validationResult'; review.prepend(box); }
    box.className = errors.length ? 'security-note validation-error' : 'security-note validation-ok';
    box.textContent = errors.length ? errors.join(' ') : 'Draft is valid and ready to create.';
    errors.length ? toast('Draft needs attention') : toast('Draft validated');
    return !errors.length;
  }
  $('#validateBot').addEventListener('click', () => showValidation(validationErrors()));
  $('#botForm').addEventListener('submit', event => {
    event.preventDefault();
    const errors = validationErrors(); if (!showValidation(errors)) return;
    const name = $('#botName').value.trim();
    const runtime = $('input[name=runtime]:checked').value;
    const browser = $('#browserProfile').value === 'none' ? 'NONE' : (runtime === 'mac' ? 'MAC-OWNED' : 'RECOVERING');
    state.bots[name] = { title: $('#botTitle').value.trim(), runtime, browser, online: runtime === 'server' || state.macOnline };
    const row = document.createElement('button'); row.type = 'button'; row.className = 'bot-row'; row.dataset.bot = name;
    row.innerHTML = `<span class="avatar">${escapeHtml(name[0].toUpperCase())}</span><span><b>${escapeHtml(name)}</b><small>${escapeHtml(state.bots[name].title)} · ${runtime === 'mac' ? 'johan-mac' : 'server'}</small></span><i class="status ${state.bots[name].online ? 'online' : 'offline'}">${state.bots[name].online ? (browser === 'RECOVERING' ? 'recovering' : 'online') : 'laptop_unavailable'}</i>`;
    row.addEventListener('click', () => selectBot(name)); $('#newBotRows').append(row);
    activity(`Created ${name} on ${runtime}; browser ${browser}`); selectBot(name);
    appendMessage($('#canonicalLog'), 'system-line', '', `${name} created with independent profile ownership. ${runtime === 'mac' ? 'Work pauses while johan-mac is offline; mutations need local approval.' : 'Dedicated server isolation provisioned.'}`);
  });

  function appendMessage(log, className, author, text) {
    const article = document.createElement('article'); article.className = className;
    if (author) { const b = document.createElement('b'); b.textContent = author; article.append(b); }
    const p = document.createElement('p'); p.textContent = text; article.append(p);
    const time = document.createElement('time'); time.textContent = 'now'; article.append(time); log.append(article); log.scrollTop = log.scrollHeight;
  }
  $('#canonicalForm').addEventListener('submit', event => {
    event.preventDefault(); const input = $('#canonicalInput'); const text = input.value.trim(); if (!text) return;
    appendMessage($('#canonicalLog'), 'message human', 'you', text); input.value = '';
    const mention = (text.match(/@([a-z][a-z0-9-]*)/) || [])[1];
    if (mention && state.bots[mention]) appendMessage($('#canonicalLog'), 'system-line', '', `Delegated to ${mention}; target permissions remain unchanged.`);
    appendMessage($('#canonicalLog'), 'message bot', state.selectedBot, mention ? `I routed that DM to ${mention} with attribution.` : 'Received in this persistent canonical Bot Chat.');
    activity(`Message sent in ${state.selectedBot} canonical chat`);
  });

  function renderMembers() {
    $('#members').innerHTML = state.room.map(name => `<span data-member="${escapeHtml(name)}">${escapeHtml(name[0].toUpperCase())} ${escapeHtml(name)} <button aria-label="Remove ${escapeHtml(name)} from room" ${name === 'chief' ? 'disabled' : ''}>×</button></span>`).join('');
    $$('#members button:not([disabled])').forEach(button => button.addEventListener('click', () => {
      const name = button.parentElement.dataset.member; state.room = state.room.filter(member => member !== name);
      renderMembers(); activity(`Removed ${name} from Launch room`);
    }));
    renderState();
  }
  $('#addLaptop').addEventListener('click', () => {
    if (!state.macOnline) { toast('johan-mac is unavailable; reconnect it in Operate'); activity('Could not add laptop-worker: Mac unavailable'); return; }
    if (!state.room.includes('laptop-worker')) state.room.push('laptop-worker');
    renderMembers(); activity('Added laptop-worker to Launch room');
  });
  $('#roomForm').addEventListener('submit', event => {
    event.preventDefault(); const input = $('#roomInput'); const text = input.value.trim(); if (!text) return;
    appendMessage($('#roomLog'), 'message human', 'you', text);
    const mentioned = [...new Set([...text.matchAll(/@([a-z][a-z0-9-]*)/g)].map(match => match[1]))];
    const eligible = mentioned.length ? mentioned.filter(name => state.room.includes(name)) : [...state.room];
    const unavailable = mentioned.filter(name => !state.room.includes(name) || !state.bots[name]?.online);
    eligible.filter(name => state.bots[name]?.online).forEach(name => appendMessage($('#roomLog'), 'message bot', name, `Received via @mention routing. Acting only with my own authority.`));
    if (unavailable.length) appendMessage($('#roomLog'), 'system-line', '', `Not routed: ${unavailable.join(', ')} unavailable or not a room member.`);
    if (!eligible.length) appendMessage($('#roomLog'), 'system-line', '', 'No eligible room member; no work dispatched.');
    input.value = ''; activity(`Room message routed to ${eligible.filter(name => state.bots[name]?.online).join(', ') || 'none'}`);
  });

  $('#channelForm').addEventListener('submit', event => {
    event.preventDefault(); const label = $('#channelLabel').value.trim(); const alias = $('#senderAlias').value.trim();
    if (!label || !/^human:[a-z0-9_-]+$/i.test(alias)) { $('#channelResult').innerHTML = '<div class="security-note validation-error">Enter a label and a human:name display alias. Numeric Telegram user/chat allowlists still enforce access.</div>'; toast('Mapping needs attention'); return; }
    state.channel = { label, alias, bot: $('#channelBot').value, mode: $('#routeMode').value };
    $('#channelResult').innerHTML = `<div class="security-note validation-ok"><b>Mapped.</b> ${escapeHtml(label)} routes by outbound polling to ${escapeHtml(state.channel.bot)}. Telegram session remains separate from canonical Bot Chat.</div>`;
    activity(`Saved Telegram mapping to ${state.channel.bot}`); toast('Channel mapping saved');
  });

  $('#toggleLaptop').addEventListener('click', () => {
    state.macOnline = !state.macOnline; state.bots['laptop-worker'].online = state.macOnline;
    $('#laptopStatus').className = `status ${state.macOnline ? 'online' : 'offline'}`; $('#laptopStatus').textContent = state.macOnline ? 'online · approval gated' : 'laptop_unavailable';
    $('#macConnection').textContent = state.macOnline ? 'johan-mac connected' : 'johan-mac unavailable';
    $('#toggleLaptop').textContent = state.macOnline ? 'Simulate Mac disconnect' : 'Simulate Mac reconnect';
    activity(`johan-mac ${state.macOnline ? 'reconnected; queued routines may resume after approval' : 'disconnected; Mac work paused'}`);
  });

  const transitions = { AUTOMATION: 'DRAINING', DRAINING: 'HUMAN', HUMAN: 'RECOVERING', RECOVERING: 'AUTOMATION' };
  const actionLabels = { AUTOMATION: 'Request human takeover', DRAINING: 'Complete drain & enter HUMAN', HUMAN: 'Release human control', RECOVERING: 'Run safe recovery probe' };
  $$('.browserAction').forEach(button => button.addEventListener('click', () => {
    const botName = button.dataset.bot; const bot = state.bots[botName]; const before = bot.browser; bot.browser = transitions[before] || 'RECOVERING';
    const badge = botName === 'chief' ? $('#chiefBrowser') : $('#testBrowser'); badge.textContent = bot.browser; badge.className = `state ${bot.browser.toLowerCase()}`;
    button.textContent = actionLabels[bot.browser]; activity(`${botName} browser ${before} → ${bot.browser}`);
    toast(bot.browser === 'HUMAN' ? 'Single-use takeover active' : `Browser is ${bot.browser}`);
  }));
  $$('.runRoutine').forEach(button => button.addEventListener('click', () => {
    const name = button.dataset.routine; const result = state.routines[name];
    toast(`${name}: ${result}`); activity(`Inspected routine ${name}: ${result}`);
  }));
  $('#copyState').addEventListener('click', async () => {
    const text = $('#liveState').innerText;
    try { await navigator.clipboard.writeText(text); toast('State copied'); }
    catch (_) { toast('Clipboard unavailable; state remains visible'); }
  });

  renderMembers(); renderState();
})();
