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
      chief: { title: 'Coordinator', runtime: 'server', browser: 'AUTOMATION', online: true, memoryMode: 'independent-empty', capabilities: ['delegation'], provider: 'openai-codex', model: 'gpt-5.6-sol' },
      'test-worker': { title: 'Safe tester', runtime: 'server', browser: 'RECOVERING', online: true, memoryMode: 'independent-empty', capabilities: ['terminal'], provider: 'openai-codex', model: 'gpt-5.6-sol' },
      'laptop-worker': { title: 'Mac operator', runtime: 'mac', browser: 'NONE', online: false, memoryMode: 'independent-empty', capabilities: ['files'], provider: 'openai-codex', model: 'gpt-5.6-sol' }
    },
    room: ['chief', 'test-worker'], channel: null,
    routines: {
      'Daily fleet brief': { owner: 'chief', schedule: '08:30 daily', result: 'success' },
      'Acceptance smoke': { owner: 'test-worker', schedule: 'every 6h', result: 'failed' },
      'Agent Inbox review': { owner: 'laptop-worker', schedule: '09:00 weekdays', result: 'paused offline' }
    },
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
    const channel = state.channel ? `${state.channel.label} → ${state.channel.ownerBot}; user ${state.channel.allowlistedUserId}; chat ${state.channel.allowlistedChatId}; ${state.channel.pairingState}/${state.channel.admissionState}` : 'not mapped';
    return `<dl><dt>Variant</dt><dd>${escapeHtml(state.variant)}</dd><dt>View</dt><dd>${escapeHtml(state.view)}</dd><dt>Selected Bot</dt><dd>${escapeHtml(state.selectedBot)}</dd><dt>Runtime</dt><dd>${escapeHtml(bot.runtime)}</dd><dt>Browser</dt><dd>${escapeHtml(bot.browser)}</dd><dt>Memory</dt><dd>${escapeHtml(bot.memoryMode || 'not recorded')}</dd><dt>Capabilities</dt><dd>${bot.capabilities?.length ? bot.capabilities.map(escapeHtml).join(', ') : 'none'}</dd><dt>Room members</dt><dd>${state.room.map(escapeHtml).join(', ')}</dd><dt>Mac</dt><dd>${state.macOnline ? 'connected' : 'unavailable'}</dd><dt>Channel</dt><dd>${escapeHtml(channel)}</dd></dl>`;
  }
  function renderState() {
    $('#liveState').innerHTML = stateMarkup();
    const bot = state.bots[state.selectedBot];
    $('#chatMeta').innerHTML = `<span>profile: ${escapeHtml(state.selectedBot)}</span><span>model: ${escapeHtml(`${bot.provider || 'not recorded'} / ${bot.model || 'not recorded'}`)}</span><span>memory: ${escapeHtml(bot.memoryMode || 'not recorded')}</span><span>capabilities: ${bot.capabilities?.length ? bot.capabilities.map(escapeHtml).join(', ') : 'none'}</span><span>seed: ${escapeHtml(bot.profileSeed || 'not recorded')}</span><span>skill: ${escapeHtml(bot.installedSkill || 'not recorded')}</span><span>session: canonical Bot Chat</span>`;
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

  let credentialManuallyOverridden = false;
  function defaultCredentialHandle(name = $('#botName').value.trim()) {
    return `secret://${name}/web/search`;
  }
  $('#botName').addEventListener('input', () => {
    if (!credentialManuallyOverridden) $('#credential').value = defaultCredentialHandle();
  });
  $('#credential').addEventListener('input', () => { credentialManuallyOverridden = true; });

  function validationErrors() {
    const name = $('#botName').value.trim();
    const errors = [];
    if (!/^[a-z][a-z0-9-]{2,31}$/.test(name)) errors.push('Profile name must be 3–32 lowercase letters, numbers, or hyphens and start with a letter.');
    if (state.bots[name]) errors.push('That Bot/profile name already exists.');
    if (!$('#botTitle').value.trim()) errors.push('Operator title is required.');
    if (!$('#botDescription').value.trim()) errors.push('Role / description is required.');
    if (!$('#persona').value.trim()) errors.push('Persona is required.');
    const credential = $('#credential').value.trim();
    const credentialMatch = credential.match(/^secret:\/\/([a-z0-9-]+)\/[a-z0-9/_-]+$/);
    if (!credentialMatch) errors.push('Credential must be an opaque secret:// handle, never a token value.');
    else if (credentialMatch[1] !== name) errors.push(`Credential owner must exactly match Bot/profile name ${name}.`);
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
    state.bots[name] = {
      title: $('#botTitle').value.trim(), description: $('#botDescription').value.trim(), runtime, browser,
      online: runtime === 'server' || state.macOnline, provider: $('#provider').value, model: $('#model').value,
      profileSeed: $('#profileSeed').value, memoryMode: $('#memoryMode').value, persona: $('#persona').value.trim(),
      capabilities: $$('input[name="cap"]:checked').map(input => input.value), installedSkill: $('#installedSkill').value,
      credentialHandle: $('#credential').value.trim(),
      firstRoutine: { name: $('#routineName').value.trim(), schedule: $('#routineSchedule').value.trim() }
    };
    const row = document.createElement('button'); row.type = 'button'; row.className = 'bot-row'; row.dataset.bot = name;
    row.innerHTML = `<span class="avatar">${escapeHtml(name[0].toUpperCase())}</span><span><b>${escapeHtml(name)}</b><small>${escapeHtml(state.bots[name].title)} · ${runtime === 'mac' ? 'johan-mac' : 'server'}</small></span><i class="status ${state.bots[name].online ? 'online' : 'offline'}">${state.bots[name].online ? (browser === 'RECOVERING' ? 'recovering' : 'online') : 'laptop_unavailable'}</i>`;
    row.addEventListener('click', () => selectBot(name)); $('#newBotRows').append(row);
    addBotOption($('#channelBot'), name);
    addBotOption($('#mentions'), `@${name}`, `@${name}`);
    const routine = state.bots[name].firstRoutine;
    if (routine.name) {
      state.routines[routine.name] = { owner: name, schedule: routine.schedule || 'not scheduled', result: runtime === 'mac' && !state.macOnline ? 'paused offline' : 'not run' };
      appendRoutineRow(routine.name, state.routines[routine.name]);
    }
    renderRoomBotOptions(name);
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
    renderRoomBotOptions();
    renderState();
  }
  function addBotOption(select, value, label = value) {
    if ([...select.options].some(option => option.value === value)) return;
    const option = document.createElement('option'); option.value = value; option.textContent = label; select.append(option);
  }
  function renderRoomBotOptions(preferred) {
    const select = $('#roomBot');
    const previous = preferred || select.value;
    const available = Object.keys(state.bots).filter(name => !state.room.includes(name));
    select.innerHTML = '';
    available.forEach(name => addBotOption(select, name, `${name}${state.bots[name].online ? '' : ' · offline'}`));
    if (available.includes(previous)) select.value = previous;
    $('#addRoomBot').disabled = !available.length;
  }
  $('#addRoomBot').addEventListener('click', () => {
    const name = $('#roomBot').value;
    if (!name || !state.bots[name] || state.room.includes(name)) return;
    state.room.push(name);
    renderMembers(); activity(`Added ${name} to Launch room${state.bots[name].online ? '' : ' (currently offline)'}`);
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
    const userIdText = $('#telegramUserId').value.trim(); const chatIdText = $('#telegramChatId').value.trim();
    const strictInteger = text => /^-?(?:0|[1-9][0-9]*)$/.test(text) && Number.isSafeInteger(Number(text));
    const pairingState = $('#pairingState').value; const admissionState = $('#admissionState').value;
    const problems = [];
    if (!label) problems.push('Enter a channel label.');
    if (!/^human:[a-z0-9_-]+$/i.test(alias)) problems.push('Enter a human:name display alias.');
    if (!strictInteger(userIdText) || Number(userIdText) <= 0) problems.push('Telegram user ID must be a strict positive integer.');
    if (!strictInteger(chatIdText) || Number(chatIdText) === 0) problems.push('Telegram chat ID must be a strict non-zero integer.');
    if (pairingState !== 'paired' || admissionState !== 'approved') problems.push('Mapping requires paired and approved admission state.');
    const ownerBot = $('#channelBot').value;
    const expectedCredential = `secret://${ownerBot}/telegram/gateway`;
    if ($('#channelCredential').value !== expectedCredential) problems.push('Credential handle must belong to the selected owning Bot.');
    if (problems.length) { $('#channelResult').innerHTML = `<div class="security-note validation-error">${escapeHtml(problems.join(' '))} Alias is display-only and cannot authorize this mapping.</div>`; toast('Mapping needs attention'); return; }
    state.channel = { label, displayAlias: alias, ownerBot, mode: $('#routeMode').value,
      allowlistedUserId: Number(userIdText), allowlistedChatId: Number(chatIdText), pairingState, admissionState,
      credentialHandle: expectedCredential };
    $('#channelResult').innerHTML = `<div class="security-note validation-ok"><b>Mapped.</b> ${escapeHtml(label)} routes by outbound polling to ${escapeHtml(state.channel.ownerBot)}. Numeric user ${state.channel.allowlistedUserId} and chat ${state.channel.allowlistedChatId} are paired and approved. Alias is display-only. Telegram session remains separate from canonical Bot Chat.</div>`;
    activity(`Saved Telegram mapping to ${state.channel.ownerBot}`); toast('Channel mapping saved');
  });

  function updateChannelCredential() {
    $('#channelCredential').value = `secret://${$('#channelBot').value}/telegram/gateway`;
  }
  $('#channelBot').addEventListener('change', updateChannelCredential);
  updateChannelCredential();

  $('#toggleLaptop').addEventListener('click', () => {
    state.macOnline = !state.macOnline;
    Object.entries(state.bots).filter(([, bot]) => bot.runtime === 'mac').forEach(([name, bot]) => {
      bot.online = state.macOnline;
      const row = $(`.bot-row[data-bot="${name}"] .status`);
      if (row) { row.className = `status ${bot.online ? 'online' : 'offline'}`; row.textContent = bot.online ? (bot.browser === 'RECOVERING' ? 'recovering' : 'online') : 'laptop_unavailable'; }
    });
    $('#laptopStatus').className = `status ${state.macOnline ? 'online' : 'offline'}`; $('#laptopStatus').textContent = state.macOnline ? 'online · approval gated' : 'laptop_unavailable';
    $('#macConnection').textContent = state.macOnline ? 'johan-mac connected' : 'johan-mac unavailable';
    $('#toggleLaptop').textContent = state.macOnline ? 'Simulate Mac disconnect' : 'Simulate Mac reconnect';
    renderRoomBotOptions();
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
  function appendRoutineRow(name, routine) {
    const row = document.createElement('tr');
    const resultClass = routine.result === 'failed' ? 'error' : routine.result.includes('offline') ? 'offline' : 'online';
    row.innerHTML = `<td>${escapeHtml(name)}</td><td>${escapeHtml(routine.owner)}</td><td>${escapeHtml(routine.schedule)}</td><td><span class="status ${resultClass}">${escapeHtml(routine.result)}</span></td><td><button class="text-button runRoutine" data-routine="${escapeHtml(name)}">Inspect</button></td>`;
    $('#routineRows').append(row);
  }
  $('#routineRows').addEventListener('click', event => {
    const button = event.target.closest('.runRoutine'); if (!button) return;
    const name = button.dataset.routine; const routine = state.routines[name]; if (!routine) return;
    toast(`${name}: ${routine.result}`); activity(`Inspected routine ${name}: ${routine.result}`);
  });
  $('#copyState').addEventListener('click', async () => {
    const text = $('#liveState').innerText;
    try { await navigator.clipboard.writeText(text); toast('State copied'); }
    catch (_) { toast('Clipboard unavailable; state remains visible'); }
  });

  renderMembers(); renderState();
})();
