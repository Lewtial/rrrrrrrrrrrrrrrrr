(() => {
  'use strict';

  const $ = (selector) => document.querySelector(selector);
  const HISTORY_KEY = 'onda.conversions.v1';
  const TERMINAL = new Set(['completed', 'failed']);
  const AUDIO_EXTENSION = /\.(mp3|wav|flac|ogg|opus|m4a|aac|aiff|aif|wma|webm|mp4)$/i;
  const state = { source: 'url', files: [], busy: false, ffmpeg: true, job: null, pollTimer: null, pollGeneration: 0, pollErrors: 0, history: readHistory(), ignoredHistoryIds: new Set(), limits: { maxFileMB: 200, maxBatchMB: 400, maxFiles: 50, maxUrls: 20, ttlHours: 24 } };
  let toastTimer;

  function element(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function icon(name) {
    const node = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    node.setAttribute('class', 'icon');
    node.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `#i-${name}`);
    node.append(use);
    return node;
  }

  function showToast(message) {
    clearTimeout(toastTimer);
    $('#toast').textContent = message;
    $('#toast').hidden = false;
    toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 4500);
  }

  function showFormError(message, focusTarget) {
    $('#form-error').textContent = message;
    $('#form-error').hidden = false;
    if (focusTarget) focusTarget.focus();
  }

  function clearFormError() {
    $('#form-error').hidden = true;
    $('#form-error').textContent = '';
  }

  function format() {
    return document.querySelector('input[name="format"]:checked').value;
  }

  function updateFormat() {
    $('#convert-label').textContent = state.busy ? 'Convirtiendo…' : `Convertir a ${format().toUpperCase()}`;
    const wav = format() === 'wav';
    $('#bit-depth-setting').hidden = !wav;
    $('#bit-depth').disabled = state.busy || !wav;
  }

  function setBusy(busy) {
    state.busy = busy;
    $('#converter-form').setAttribute('aria-busy', String(busy));
    $('#convert-button').disabled = busy || !state.ffmpeg;
    $('#convert-button .spinner').hidden = !busy;
    $('#convert-button .button-arrow').hidden = busy;
    $('#close-results').disabled = busy;
    for (const control of document.querySelectorAll('#converter-form input, #converter-form textarea, #converter-form select, #selected-files button, #paste-button, .source-tab')) control.disabled = busy;
    updateFormat();
  }

  function setSource(source, focus = false) {
    if (state.busy) return;
    state.source = source;
    clearFormError();
    for (const type of ['url', 'file']) {
      const active = type === source;
      const tab = $(`#tab-${type}`);
      tab.classList.toggle('active', active);
      tab.setAttribute('aria-selected', String(active));
      tab.tabIndex = active ? 0 : -1;
      $(`#panel-${type}`).hidden = !active;
      if (active && focus) tab.focus();
    }
  }

  function fileSize(bytes) {
    if (bytes >= 1024 * 1024) return `${(bytes / 1024 / 1024).toFixed(1)} MB`;
    return `${Math.max(1, Math.round(bytes / 1024))} KB`;
  }

  function renderFiles() {
    const list = $('#selected-files');
    list.replaceChildren();
    list.hidden = state.files.length === 0;
    for (const [index, file] of state.files.entries()) {
      const row = element('div', 'selected-file');
      row.append(icon('music'), element('span', 'selected-file-name', file.name), element('span', 'selected-file-size', fileSize(file.size)));
      const remove = element('button');
      remove.type = 'button';
      remove.setAttribute('aria-label', `Quitar ${file.name}`);
      remove.append(icon('close'));
      remove.disabled = state.busy;
      remove.addEventListener('click', () => { state.files.splice(index, 1); renderFiles(); });
      row.append(remove);
      list.append(row);
    }
  }

  function addFiles(files) {
    if (state.busy) return;
    clearFormError();
    const incoming = Array.from(files);
    const oversized = incoming.find((file) => file.size > state.limits.maxFileMB * 1024 * 1024);
    if (oversized) return showFormError(`«${oversized.name}» supera los ${state.limits.maxFileMB} MB. Elige un archivo más pequeño.`);
    const empty = incoming.find((file) => file.size === 0);
    if (empty) return showFormError(`«${empty.name}» está vacío. Selecciona un archivo que contenga audio.`);
    const notAudio = incoming.find((file) => !AUDIO_EXTENSION.test(file.name));
    if (notAudio) return showFormError(`«${notAudio.name}» no parece un archivo de audio. Selecciona MP3, WAV, FLAC, M4A u otro formato de audio.`);
    const unique = [...state.files];
    for (const file of incoming) {
      if (!unique.some((other) => other.name === file.name && other.size === file.size && other.lastModified === file.lastModified)) unique.push(file);
    }
    if (unique.length > state.limits.maxFiles) return showFormError(`Puedes añadir hasta ${state.limits.maxFiles} archivos en una conversión. Divide tu selección en varios lotes.`);
    if (unique.reduce((sum, file) => sum + file.size, 0) > state.limits.maxBatchMB * 1024 * 1024) return showFormError(`El lote completo puede ocupar hasta ${state.limits.maxBatchMB} MB. Divide tu selección en varios lotes.`);
    state.files = unique;
    renderFiles();
    $('#source-files').value = '';
  }

  function parseUrls() {
    const urls = $('#source-urls').value.split(/[\s,]+/).map((value) => value.trim()).filter(Boolean);
    if (!urls.length) throw new Error('Pega al menos un enlace de SoundCloud para empezar.');
    if (urls.length > state.limits.maxUrls) throw new Error(`Puedes convertir hasta ${state.limits.maxUrls} enlaces en un lote.`);
    for (const value of urls) {
      let url;
      try { url = new URL(value); } catch { throw new Error('Revisa los enlaces: cada uno debe empezar por https://soundcloud.com/ o https://on.soundcloud.com/.'); }
      const host = url.hostname.toLowerCase();
      if (url.protocol !== 'https:' || !['soundcloud.com', 'www.soundcloud.com', 'm.soundcloud.com', 'on.soundcloud.com'].includes(host) || url.username || url.password || url.port) throw new Error('Solo se aceptan enlaces HTTPS de SoundCloud. Revisa cada enlace y colócalo en una línea.');
      if (!url.pathname || url.pathname === '/') throw new Error('Pega el enlace de una pista o playlist, no el de la página de inicio.');
    }
    return [...new Set(urls)];
  }

  async function api(url, options = {}) {
    let response;
    try { response = await fetch(url, { ...options, headers: { Accept: 'application/json', ...options.headers } }); }
    catch { throw new Error('No se pudo conectar con el conversor. Comprueba tu conexión e inténtalo de nuevo.'); }
    let data;
    try { data = await response.json(); } catch { throw new Error('El servicio no devolvió una respuesta válida. Inténtalo de nuevo en unos momentos.'); }
    if (!response.ok) {
      if (response.status === 404) throw new Error(`Esta conversión ya no está disponible. Los archivos se eliminan después de ${state.limits.ttlHours} horas. Puedes volver a convertir el audio.`);
      const detail = data.detail || data.error || data.message;
      if (typeof detail === 'string') throw new Error(detail);
      if (Array.isArray(detail)) throw new Error('No se pudo procesar la solicitud. Revisa los enlaces, los archivos y los ajustes seleccionados.');
      throw new Error(response.status === 429 ? 'El conversor está ocupado. Espera unos momentos e inténtalo de nuevo.' : 'No se pudo completar la solicitud. Inténtalo de nuevo.');
    }
    return data;
  }

  function readHistory() {
    try {
      const items = JSON.parse(localStorage.getItem(HISTORY_KEY) || '[]');
      return Array.isArray(items) ? items.filter((item) => item && typeof item.id === 'string' && /^[a-zA-Z0-9_-]{1,100}$/.test(item.id)).slice(0, 20) : [];
    } catch { return []; }
  }

  function saveHistory() {
    try { localStorage.setItem(HISTORY_KEY, JSON.stringify(state.history.slice(0, 20))); } catch { /* Conversion still works when browser storage is disabled. */ }
    renderHistory();
  }

  function rememberJob(job, fallbackTitle) {
    if (state.ignoredHistoryIds.has(job.id)) return;
    const previous = state.history.find((entry) => entry.id === job.id);
    const firstTrack = Array.isArray(job.tracks) && job.tracks[0];
    const title = firstTrack?.title || previous?.title || fallbackTitle || 'Conversión de audio';
    const item = { id: job.id, title, format: job.format || previous?.format || format(), createdAt: previous?.createdAt || job.created_at || new Date().toISOString(), status: job.status };
    state.history = [item, ...state.history.filter((entry) => entry.id !== job.id)].slice(0, 20);
    saveHistory();
  }

  function historyDate(value) {
    try { return new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value)); } catch { return ''; }
  }

  function renderHistory() {
    const count = $('#history-count');
    count.textContent = String(state.history.length);
    count.hidden = state.history.length === 0;
    const list = $('#history-list');
    list.replaceChildren();
    $('#clear-history').disabled = state.history.length === 0;
    if (!state.history.length) {
      list.append(element('p', 'history-empty', 'Tu próxima conversión empieza una nueva historia. Aquí aparecerán tus últimas pistas.'));
      return;
    }
    const statuses = { completed: 'Completada', failed: 'No completada', processing: 'En proceso', queued: 'En cola' };
    for (const entry of state.history) {
      const row = element('button', 'history-item');
      row.type = 'button';
      row.append(icon('music'));
      const body = element('span');
      body.append(element('span', 'history-job-title', entry.title), element('span', 'history-job-meta', [String(entry.format || '').toUpperCase(), historyDate(entry.createdAt), statuses[entry.status] || 'Conversión'].filter(Boolean).join(' · ')));
      row.append(body, icon('arrow'));
      row.addEventListener('click', () => openHistoryJob(entry.id));
      list.append(row);
    }
  }

  function safeDownloadUrl(value) {
    if (typeof value !== 'string') return null;
    try {
      const url = new URL(value, window.location.origin);
      return url.origin === window.location.origin && /^\/api\/jobs\/[a-zA-Z0-9_-]+\/(?:download\/[a-zA-Z0-9_-]+|zip)$/.test(url.pathname) ? url.href : null;
    } catch { return null; }
  }

  function duration(value) {
    const seconds = Number(value);
    if (!Number.isFinite(seconds) || seconds < 0) return '';
    return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`;
  }

  function renderTracks(tracks) {
    const list = $('#track-list');
    list.replaceChildren();
    for (const track of tracks) {
      const row = element('div', 'track-row');
      const visual = element('span', 'track-icon');
      visual.append(icon(track.status === 'completed' ? 'check' : track.status === 'failed' ? 'alert' : 'music'));
      const body = element('div', 'track-info');
      body.append(element('div', 'track-title', track.title || 'Pista de audio'));
      const subtitle = [track.artist, duration(track.duration), track.filename].filter(Boolean).join(' · ');
      if (track.error) body.append(element('div', 'track-subtitle track-error', track.error));
      else if (subtitle) body.append(element('div', 'track-subtitle', subtitle));
      row.append(visual, body);
      const downloadUrl = safeDownloadUrl(track.download_url);
      if (track.status === 'completed' && downloadUrl) {
        const download = element('a', 'track-download');
        download.href = downloadUrl;
        download.download = track.filename || '';
        download.setAttribute('aria-label', `Descargar ${track.title || 'pista'}`);
        download.append(icon('download'), element('span', '', 'Descargar'));
        row.append(download);
      } else {
        const labels = { queued: 'En cola', processing: 'Convirtiendo…', completed: 'Completada', failed: 'No disponible' };
        row.append(element('span', `track-status ${track.status === 'failed' ? 'failed' : ''}`, labels[track.status] || 'Preparando…'));
      }
      list.append(row);
    }
  }

  function renderJob(job) {
    state.job = job;
    const terminal = TERMINAL.has(job.status);
    const failed = job.status === 'failed';
    const tracks = Array.isArray(job.tracks) ? job.tracks : [];
    const completed = tracks.filter((track) => track.status === 'completed').length;
    const failedTracks = tracks.filter((track) => track.status === 'failed').length;
    $('#results').hidden = false;
    $('#results-title').textContent = failed ? 'No pudimos convertir este audio' : terminal ? (failedTracks ? 'Tu audio está listo, con avisos' : 'Tu audio, listo para sonar.') : 'Tu música está en camino…';
    $('#job-message').textContent = job.message || job.error || (failed ? 'Revisa el origen del audio e inténtalo de nuevo.' : terminal ? `${completed} ${completed === 1 ? 'pista lista' : 'pistas listas'} para descargar` : 'Preparando la conversión…');
    if (failed && job.error && job.error !== job.message) $('#job-message').textContent = job.error;
    const value = Math.max(0, Math.min(100, Number(job.progress) || 0));
    $('#progress-label').textContent = `${Math.round(value)}%`;
    $('#progress-fill').style.width = `${value}%`;
    $('#progress-fill').style.background = failed ? 'var(--red)' : terminal ? 'var(--green)' : 'var(--orange)';
    $('#job-progress').setAttribute('aria-valuenow', String(Math.round(value)));
    renderTracks(tracks);
    $('#result-actions').hidden = !terminal;
    const zipUrl = safeDownloadUrl(job.zip_url);
    $('#download-zip').hidden = !zipUrl;
    if (zipUrl) $('#download-zip').href = zipUrl;
    else $('#download-zip').removeAttribute('href');
    if (terminal) setBusy(false);
    rememberJob(job);
  }

  function stopPolling() {
    clearTimeout(state.pollTimer);
    state.pollGeneration += 1;
  }

  async function pollJob(id, generation) {
    if (generation !== state.pollGeneration) return;
    try {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
      if (generation !== state.pollGeneration) return;
      state.pollErrors = 0;
      $('#poll-error').hidden = true;
      $('#retry-poll').hidden = true;
      renderJob(job);
      if (!TERMINAL.has(job.status)) state.pollTimer = setTimeout(() => pollJob(id, generation), 1000);
    } catch (error) {
      if (generation !== state.pollGeneration) return;
      state.pollErrors += 1;
      $('#poll-error').textContent = `${error.message} La conversión puede continuar en el servidor.`;
      $('#poll-error').hidden = false;
      if (state.pollErrors < 3) state.pollTimer = setTimeout(() => pollJob(id, generation), 2000);
      else {
        $('#retry-poll').hidden = false;
        $('#close-results').disabled = false;
        $('#job-message').textContent = 'Comprobación pausada. Vuelve a consultar el estado para recuperar la descarga.';
      }
    }
  }

  function startPolling(job) {
    stopPolling();
    state.pollErrors = 0;
    $('#poll-error').hidden = true;
    $('#retry-poll').hidden = true;
    renderJob(job);
    if (!TERMINAL.has(job.status)) state.pollTimer = setTimeout(() => pollJob(job.id, state.pollGeneration), 700);
  }

  async function openHistoryJob(id) {
    if (state.busy && state.job?.id !== id) return showToast('Espera a que termine la conversión actual para abrir otra.');
    try {
      const job = await api(`/api/jobs/${encodeURIComponent(id)}`);
      setBusy(!TERMINAL.has(job.status));
      startPolling(job);
      $('#results').scrollIntoView({ behavior: 'smooth', block: 'start' });
      $('#results-title').focus({ preventScroll: true });
    } catch (error) { showToast(error.message); }
  }

  function dismissResults() {
    if (state.busy && $('#retry-poll').hidden) return;
    stopPolling();
    setBusy(false);
    state.job = null;
    $('#results').hidden = true;
    $('#poll-error').hidden = true;
    $('#retry-poll').hidden = true;
    $('#converter').scrollIntoView({ behavior: 'smooth', block: 'start' });
    if (state.source === 'url') $('#source-urls').focus({ preventScroll: true });
    else $('#source-files').focus({ preventScroll: true });
  }

  async function submit(event) {
    event.preventDefault();
    if (state.busy || !state.ffmpeg) return;
    clearFormError();
    let options;
    let endpoint;
    let title;
    try {
      const settings = { format: format(), sample_rate: Number($('#sample-rate').value), bit_depth: Number($('#bit-depth').value), normalize: $('#normalize').checked };
      if (state.source === 'url') {
        const urls = parseUrls();
        endpoint = '/api/jobs';
        title = urls.length === 1 ? 'Pista de SoundCloud' : `${urls.length} enlaces de SoundCloud`;
        options = { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify({ urls, ...settings }) };
      } else {
        if (!state.files.length) throw new Error('Selecciona al menos un archivo de audio para empezar.');
        if (state.files.length > state.limits.maxFiles) throw new Error(`Puedes añadir hasta ${state.limits.maxFiles} archivos por conversión.`);
        if (state.files.some((file) => file.size > state.limits.maxFileMB * 1024 * 1024)) throw new Error(`Cada archivo puede ocupar hasta ${state.limits.maxFileMB} MB. Quita los archivos más grandes.`);
        if (state.files.reduce((sum, file) => sum + file.size, 0) > state.limits.maxBatchMB * 1024 * 1024) throw new Error(`El lote completo puede ocupar hasta ${state.limits.maxBatchMB} MB. Quita algunos archivos.`);
        const body = new FormData();
        for (const file of state.files) body.append('files', file, file.name);
        for (const [key, value] of Object.entries(settings)) body.append(key, String(value));
        endpoint = '/api/uploads';
        title = state.files.length === 1 ? state.files[0].name : `${state.files.length} archivos de audio`;
        options = { method: 'POST', body };
      }
      setBusy(true);
      const job = await api(endpoint, options);
      if (!job || typeof job.id !== 'string') throw new Error('El conversor no devolvió un identificador. Inténtalo de nuevo.');
      rememberJob(job, title);
      startPolling(job);
      $('#results').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
      $('#results-title').focus({ preventScroll: true });
    } catch (error) {
      setBusy(false);
      showFormError(error.message, state.source === 'url' ? $('#source-urls') : null);
    }
  }

  async function checkHealth() {
    try {
      const health = await api('/api/health');
      state.ffmpeg = health.ffmpeg !== false;
      const limit = (value, fallback) => Number.isFinite(Number(value)) && Number(value) > 0 ? Number(value) : fallback;
      state.limits.maxFileMB = limit(health.max_upload_mb, state.limits.maxFileMB);
      state.limits.maxBatchMB = limit(health.max_batch_upload_mb, state.limits.maxBatchMB);
      state.limits.maxFiles = limit(health.max_tracks, state.limits.maxFiles);
      state.limits.maxUrls = limit(health.max_urls, state.limits.maxUrls);
      state.limits.ttlHours = limit(health.job_ttl_hours, state.limits.ttlHours);
      $('#upload-limit-help').textContent = `MP3, WAV, FLAC, M4A, OGG y otros formatos de audio · Máx. ${state.limits.maxFileMB} MB por archivo y ${state.limits.maxBatchMB} MB por lote`;
      $('#url-help').textContent = `Una pista, una playlist o varios enlaces, uno por línea. Máx. ${state.limits.maxUrls} enlaces por lote.`;
      $('#history-retention-help').textContent = `Tus últimas 20 conversiones. Los archivos están disponibles durante ${state.limits.ttlHours} horas.`;
      $('#privacy-copy').textContent = `Se procesan en el servidor para la conversión y se eliminan automáticamente después de ${state.limits.ttlHours} horas. El historial se guarda solo en este navegador; borrarlo no cambia el plazo de eliminación de los archivos del servidor.`;
      if (!state.ffmpeg) {
        $('#service-notice').textContent = 'El servidor necesita FFmpeg para convertir audio. Cuando esté disponible podrás iniciar la conversión.';
        $('#service-notice').hidden = false;
        $('#convert-button').disabled = true;
      }
    } catch {
      $('#service-notice').textContent = 'No pudimos comprobar el estado del servicio. Puedes intentarlo; si no responde, vuelve en unos momentos.';
      $('#service-notice').hidden = false;
    }
  }

  $('#tab-url').addEventListener('click', () => setSource('url'));
  $('#tab-file').addEventListener('click', () => setSource('file'));
  for (const tab of document.querySelectorAll('.source-tab')) tab.addEventListener('keydown', (event) => {
    if (['ArrowLeft', 'ArrowRight', 'Home', 'End'].includes(event.key)) {
      event.preventDefault();
      const source = event.key === 'Home' ? 'url' : event.key === 'End' ? 'file' : state.source === 'url' ? 'file' : 'url';
      setSource(source, true);
    }
  });
  $('#paste-button').addEventListener('click', async () => {
    try {
      if (!navigator.clipboard?.readText) throw new Error('clipboard unavailable');
      const text = await navigator.clipboard.readText();
      if (!text.trim()) return showToast('El portapapeles está vacío. Copia un enlace de SoundCloud primero.');
      $('#source-urls').value = text.trim();
      clearFormError();
      $('#source-urls').focus();
    } catch { showToast('No se pudo acceder al portapapeles. Pega el enlace directamente en el campo.'); $('#source-urls').focus(); }
  });
  $('#source-files').addEventListener('change', (event) => addFiles(event.target.files));
  const dropZone = $('#drop-zone');
  for (const type of ['dragenter', 'dragover']) dropZone.addEventListener(type, (event) => { event.preventDefault(); if (!state.busy) dropZone.classList.add('drag-over'); });
  for (const type of ['dragleave', 'drop']) dropZone.addEventListener(type, (event) => { event.preventDefault(); dropZone.classList.remove('drag-over'); });
  dropZone.addEventListener('drop', (event) => { if (event.dataTransfer?.files) addFiles(event.dataTransfer.files); });
  for (const radio of document.querySelectorAll('input[name="format"]')) radio.addEventListener('change', updateFormat);
  $('#converter-form').addEventListener('submit', submit);
  $('#source-urls').addEventListener('input', clearFormError);
  $('#close-results').addEventListener('click', dismissResults);
  $('#new-conversion').addEventListener('click', dismissResults);
  $('#retry-poll').addEventListener('click', () => {
    if (!state.job) return;
    state.pollErrors = 0;
    $('#retry-poll').hidden = true;
    $('#close-results').disabled = true;
    pollJob(state.job.id, state.pollGeneration);
  });
  $('#history-toggle').addEventListener('click', () => {
    const panel = $('#history-panel');
    panel.hidden = !panel.hidden;
    $('#history-toggle').setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) { panel.scrollIntoView({ behavior: 'smooth', block: 'start' }); $('#history-title').focus({ preventScroll: true }); }
  });
  $('#clear-history').addEventListener('click', () => { for (const entry of state.history) state.ignoredHistoryIds.add(entry.id); state.history = []; saveHistory(); showToast('Historial borrado de este navegador.'); });
  document.addEventListener('click', (event) => {
    const download = event.target.closest('.track-download, #download-zip');
    if (download && !download.getAttribute('href')) event.preventDefault();
  });
  renderHistory();
  updateFormat();
  checkHealth();
})();
