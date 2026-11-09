(() => {
  'use strict';

  const $ = (selector) => document.querySelector(selector);
  const MiB = 1024 * 1024;
  const HISTORY_LIMIT = 10;
  const HISTORY_BYTES = 50 * MiB;
  const engine = window.OndaAudio;
  const limits = engine?.limits || { maxFileBytes: 25 * MiB, maxFiles: 10, maxTotalInputBytes: 100 * MiB, maxOutputBytes: 200 * MiB, maxDuration: 600 };
  const state = { files: [], tracks: [], converting: false, zipBusy: false, controller: null, urls: new Set(), zipURL: null, generation: 0, history: [], db: null, dbError: false, resultId: null, cachePending: 0 };
  let toastTimer;

  function el(tag, className, text) {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined) node.textContent = String(text);
    return node;
  }

  function icon(name) {
    const svg = document.createElementNS('http://www.w3.org/2000/svg', 'svg');
    svg.setAttribute('class', 'icon');
    svg.setAttribute('aria-hidden', 'true');
    const use = document.createElementNS('http://www.w3.org/2000/svg', 'use');
    use.setAttribute('href', `#i-${name}`);
    svg.append(use);
    return svg;
  }

  function id() { return window.crypto?.randomUUID ? crypto.randomUUID() : `${Date.now()}-${Math.random().toString(36).slice(2)}`; }
  function isBusy() { return state.converting || state.zipBusy; }
  function mb(bytes) { return bytes >= MiB ? `${(bytes / MiB).toFixed(1)} MiB` : `${Math.max(1, Math.round(bytes / 1024))} KiB`; }
  function time(seconds) { return `${Math.floor(seconds / 60)}:${String(Math.floor(seconds % 60)).padStart(2, '0')}`; }

  function toast(message) {
    clearTimeout(toastTimer);
    $('#toast').textContent = message;
    $('#toast').hidden = false;
    toastTimer = setTimeout(() => { $('#toast').hidden = true; }, 4500);
  }

  function error(message) { $('#form-error').textContent = message; $('#form-error').hidden = false; }
  function clearError() { $('#form-error').textContent = ''; $('#form-error').hidden = true; }

  function notice(message) {
    $('#storage-notice').textContent = message;
    $('#storage-notice').hidden = !message;
  }

  function setControls() {
    const busy = isBusy();
    $('#converter-form').setAttribute('aria-busy', String(busy));
    for (const control of document.querySelectorAll('#converter-form input, #converter-form select, #converter-form button')) control.disabled = busy;
    $('#convert-button').disabled = busy || !engine?.supported;
    $('#convert-label').textContent = state.converting ? 'Convirtiendo…' : state.zipBusy ? 'Preparando ZIP…' : 'Convertir a WAV';
    $('#convert-button .spinner').hidden = !busy;
    $('#convert-button .button-arrow').hidden = busy;
    $('#close-results').disabled = busy;
    $('#new-conversion').disabled = busy;
    $('#clear-history').disabled = busy || state.cachePending > 0 || !state.history.length;
    $('#cancel-conversion').hidden = !state.converting;
    $('#cancel-conversion').disabled = !state.converting || !!state.controller?.signal.aborted;
    $('#cancel-conversion').textContent = state.controller?.signal.aborted ? 'Cancelando…' : 'Cancelar conversión';
    $('#download-zip').setAttribute('aria-disabled', String(busy));
  }

  function validateFiles(files) {
    if (files.length > limits.maxFiles) throw new Error(`Puedes seleccionar hasta ${limits.maxFiles} archivos por lote.`);
    const large = files.find((file) => file.size > limits.maxFileBytes);
    if (large) throw new Error(`«${large.name}» supera los ${limits.maxFileBytes / MiB} MiB por archivo.`);
    const empty = files.find((file) => !file.size);
    if (empty) throw new Error(`«${empty.name}» está vacío. Elige un archivo que contenga audio.`);
    if (files.reduce((total, file) => total + file.size, 0) > limits.maxTotalInputBytes) throw new Error(`El lote puede ocupar hasta ${limits.maxTotalInputBytes / MiB} MiB de entrada. Quita algunos archivos.`);
  }

  function addFiles(fileList) {
    if (isBusy()) return;
    clearError();
    const selected = [...state.files];
    for (const file of Array.from(fileList)) {
      if (!selected.some((other) => file.name === other.name && file.size === other.size && file.lastModified === other.lastModified)) selected.push(file);
    }
    try { validateFiles(selected); } catch (failure) { error(failure.message); return; }
    state.files = selected;
    renderFiles();
    $('#source-files').value = '';
  }

  function renderFiles() {
    const list = $('#selected-files');
    list.replaceChildren();
    list.hidden = !state.files.length;
    for (const [index, file] of state.files.entries()) {
      const row = el('div', 'selected-file');
      row.append(icon('music'), el('span', 'selected-file-name', file.name), el('span', 'selected-file-size', mb(file.size)));
      const remove = el('button');
      remove.type = 'button';
      remove.disabled = isBusy();
      remove.setAttribute('aria-label', `Quitar ${file.name}`);
      remove.append(icon('close'));
      remove.addEventListener('click', () => { if (!isBusy()) { state.files.splice(index, 1); renderFiles(); } });
      row.append(remove);
      list.append(row);
    }
  }

  function makeDemo() {
    if (isBusy()) return;
    const sampleRate = 22050;
    const seconds = 1.8;
    const length = Math.floor(sampleRate * seconds);
    const buffer = new ArrayBuffer(44 + length * 2);
    const view = new DataView(buffer);
    const word = (offset, value) => { for (let i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i)); };
    word(0, 'RIFF'); view.setUint32(4, 36 + length * 2, true); word(8, 'WAVE'); word(12, 'fmt ');
    view.setUint32(16, 16, true); view.setUint16(20, 1, true); view.setUint16(22, 1, true);
    view.setUint32(24, sampleRate, true); view.setUint32(28, sampleRate * 2, true); view.setUint16(32, 2, true); view.setUint16(34, 16, true);
    word(36, 'data'); view.setUint32(40, length * 2, true);
    const notes = [261.6256, 329.6276, 391.9954];
    for (let i = 0; i < length; i++) {
      const t = i / sampleRate;
      const local = t % 0.6;
      const envelope = Math.min(1, local / 0.025) * Math.max(0, 1 - local / 0.6) ** 1.5;
      const frequency = notes[Math.min(2, Math.floor(t / 0.6))];
      const sample = Math.sin(2 * Math.PI * frequency * t) * envelope * 0.28;
      view.setInt16(44 + i * 2, Math.round(sample * 32767), true);
    }
    clearError();
    state.files = [new File([buffer], 'ejemplo-onda.wav', { type: 'audio/wav', lastModified: 0 })];
    renderFiles();
    toast('Ejemplo real preparado: pulsa «Convertir a WAV» para probarlo.');
    $('#convert-button').focus();
  }

  function objectURL(blob) {
    const url = URL.createObjectURL(blob);
    state.urls.add(url);
    return url;
  }

  function releaseURLs() {
    for (const player of document.querySelectorAll('#track-list audio')) player.pause();
    for (const url of state.urls) URL.revokeObjectURL(url);
    state.urls.clear();
    state.zipURL = null;
    $('#download-zip').href = '#';
    $('#zip-label').textContent = 'Descargar todo en ZIP';
  }

  function updateProgress(value, message) {
    const progress = Math.max(0, Math.min(100, Number(value) || 0));
    $('#progress-label').textContent = `${Math.floor(progress)}%`;
    $('#progress-fill').style.width = `${progress}%`;
    $('#job-progress').setAttribute('aria-valuenow', String(Math.floor(progress)));
    $('#job-message').textContent = message;
  }

  function renderTrack(track) {
    const row = el('div', 'track-row');
    row.dataset.trackId = track.id;
    const visual = el('span', 'track-icon');
    visual.append(icon(track.status === 'completed' ? 'check' : track.status === 'failed' ? 'alert' : 'music'));
    const info = el('div', 'track-info');
    info.append(el('div', 'track-title', track.result?.fileName || track.name));
    if (track.result) {
      const result = track.result;
      info.append(el('div', 'track-subtitle', `${time(result.duration)} · ${result.bitDepth} bits · ${result.sampleRate / 1000} kHz · Estéreo · ${mb(result.blob.size)}`));
      const player = el('audio', 'audio-preview');
      player.controls = true;
      player.preload = 'none';
      player.src = track.url;
      player.setAttribute('aria-label', `Escuchar ${result.fileName}`);
      info.append(player);
    } else if (track.error) info.append(el('div', 'track-subtitle track-error', track.error));
    else if (track.stage) info.append(el('div', 'track-subtitle', track.stage));
    row.append(visual, info);
    if (track.result) {
      const download = el('a', 'track-download');
      download.href = track.url;
      download.download = track.result.fileName;
      download.setAttribute('aria-label', `Descargar ${track.result.fileName}`);
      download.append(icon('download'), el('span', '', 'Descargar'));
      row.append(download);
    } else {
      const label = { queued: 'En cola', processing: 'Convirtiendo…', failed: 'No disponible', cancelled: 'Cancelada' };
      row.append(el('span', `track-status ${track.status === 'failed' ? 'failed' : ''}`, label[track.status] || 'Preparando…'));
    }
    return row;
  }

  function refreshTrack(track) {
    const previous = Array.from($('#track-list').children).find((node) => node.dataset.trackId === track.id);
    const replacement = renderTrack(track);
    if (previous) previous.replaceWith(replacement);
    else $('#track-list').append(replacement);
  }

  function showResultState() {
    const completed = state.tracks.filter((track) => track.result).length;
    const failed = state.tracks.filter((track) => track.status === 'failed').length;
    const cancelled = state.tracks.some((track) => track.status === 'cancelled');
    $('#results-title').textContent = cancelled ? 'Conversión detenida' : !completed ? 'No pudimos convertir este audio' : failed ? 'Tu audio está listo, con avisos' : 'Tu audio, listo para sonar.';
    $('#progress-fill').style.background = completed ? 'var(--green)' : 'var(--red)';
    if (!cancelled) updateProgress(100, `${completed} ${completed === 1 ? 'pista lista' : 'pistas listas'}${failed ? ` · ${failed} no se pudieron convertir` : ''}`);
    else $('#job-message').textContent = completed ? 'Puedes descargar las pistas que ya se convirtieron.' : 'Puedes volver a intentarlo cuando quieras.';
    $('#result-actions').hidden = false;
    $('#download-zip').hidden = !completed;
  }

  async function convert(event) {
    event.preventDefault();
    if (isBusy() || !engine?.supported) return;
    clearError();
    try { if (!state.files.length) throw new Error('Elige un archivo de audio o pulsa «Probar con un ejemplo».'); validateFiles(state.files); }
    catch (failure) { error(failure.message); return; }
    const files = [...state.files];
    const options = { sampleRate: Number($('#sample-rate').value), bitDepth: Number($('#bit-depth').value), normalize: $('#normalize').checked };
    releaseURLs();
    notice('');
    state.generation += 1;
    state.resultId = id();
    state.controller = new AbortController();
    state.tracks = files.map((file) => ({ id: id(), name: file.name, status: 'queued', result: null }));
    state.converting = true;
    $('#results').hidden = false;
    $('#results-title').textContent = 'Tu música está en camino…';
    $('#progress-fill').style.background = 'var(--orange)';
    $('#result-actions').hidden = true;
    $('#track-list').replaceChildren(...state.tracks.map(renderTrack));
    updateProgress(0, 'Preparando la conversión en tu navegador…');
    setControls();
    $('#results').scrollIntoView({ behavior: 'smooth', block: 'nearest' });
    $('#results-title').focus({ preventScroll: true });
    let bytes = 0;
    for (let index = 0; index < files.length; index++) {
      const track = state.tracks[index];
      if (state.controller.signal.aborted) { track.status = 'cancelled'; refreshTrack(track); continue; }
      track.status = 'processing';
      track.stage = 'Leyendo el archivo';
      refreshTrack(track);
      try {
        const result = await engine.convert(files[index], { ...options, maxOutputBytes: limits.maxOutputBytes - bytes }, (info) => {
          if (state.controller.signal.aborted) return;
          const progress = typeof info === 'number' ? info : info.progress;
          track.stage = typeof info === 'object' ? info.stage || 'Convirtiendo…' : 'Convirtiendo…';
          updateProgress(((index + Math.max(0, Math.min(100, Number(progress) || 0)) / 100) / files.length) * 100, `Archivo ${index + 1} de ${files.length} · ${track.stage}`);
          refreshTrack(track);
        }, state.controller.signal);
        if (state.controller.signal.aborted) { track.status = 'cancelled'; }
        else {
          track.result = result;
          track.status = 'completed';
          bytes += result.blob.size;
          track.url = objectURL(result.blob);
        }
      } catch (failure) {
        track.status = failure.name === 'AbortError' || state.controller.signal.aborted ? 'cancelled' : 'failed';
        track.error = track.status === 'failed' ? failure.message || 'El navegador no pudo decodificar este archivo. Prueba con MP3 o WAV.' : '';
      }
      refreshTrack(track);
      if (!state.controller.signal.aborted) updateProgress(((index + 1) / files.length) * 100, `Archivo ${index + 1} de ${files.length} procesado`);
    }
    state.converting = false;
    state.controller = null;
    showResultState();
    setControls();
    await cacheCurrentResult();
  }

  async function downloadZip(event) {
    if (state.zipURL && !isBusy()) return;
    event.preventDefault();
    if (isBusy()) return;
    const tracks = state.tracks.filter((track) => track.result);
    if (!tracks.length) return;
    const generation = state.generation;
    state.zipBusy = true;
    setControls();
    $('#zip-label').textContent = 'Preparando ZIP…';
    try {
      const blob = await engine.createZip(tracks.map((track) => ({ name: track.result.fileName, blob: track.result.blob })), (info) => {
        const progress = typeof info === 'number' ? info : info?.progress;
        if (Number.isFinite(progress)) $('#zip-label').textContent = `Preparando ZIP… ${Math.floor(progress)}%`;
      });
      if (generation !== state.generation) return;
      state.zipURL = objectURL(blob);
      $('#download-zip').href = state.zipURL;
      $('#zip-label').textContent = 'Descargar todo en ZIP';
      state.zipBusy = false;
      setControls();
      $('#download-zip').click();
    } catch (failure) {
      toast(failure.message || 'No se pudo preparar el ZIP. Puedes descargar cada pista por separado.');
      $('#zip-label').textContent = 'Volver a preparar ZIP';
    } finally { state.zipBusy = false; setControls(); }
  }

  function reset() {
    if (isBusy()) return;
    state.generation += 1;
    releaseURLs();
    state.tracks = [];
    state.resultId = null;
    $('#track-list').replaceChildren();
    $('#results').hidden = true;
    notice('');
    $('#converter').scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('#source-files').focus({ preventScroll: true });
  }

  function openDatabase() {
    return new Promise((resolve, reject) => {
      if (!window.indexedDB) return reject(new Error('El navegador no ofrece almacenamiento local.'));
      const request = indexedDB.open('onda-local-audio', 1);
      request.onupgradeneeded = () => { if (!request.result.objectStoreNames.contains('conversions')) request.result.createObjectStore('conversions', { keyPath: 'id' }); };
      request.onsuccess = () => { const db = request.result; db.onversionchange = () => db.close(); resolve(db); };
      request.onerror = () => reject(request.error || new Error('No se pudo abrir el almacenamiento local.'));
      request.onblocked = () => reject(new Error('Otra pestaña está usando el historial.'));
    });
  }

  function allRecords() {
    return new Promise((resolve, reject) => {
      const transaction = state.db.transaction('conversions', 'readonly');
      const request = transaction.objectStore('conversions').getAll();
      request.onsuccess = () => resolve(request.result);
      request.onerror = () => reject(request.error);
    });
  }

  async function loadHistory() {
    try {
      if (!state.db) state.db = await openDatabase();
      state.history = (await allRecords()).filter((entry) => Array.isArray(entry.tracks) && entry.tracks.every((track) => track.blob instanceof Blob)).sort((a, b) => b.createdAt - a.createdAt);
      renderHistory();
      return true;
    } catch {
      state.dbError = true;
      $('#history-notice').textContent = 'El navegador no permite guardar el historial. Tus conversiones y descargas siguen funcionando durante esta sesión.';
      $('#history-notice').hidden = false;
      renderHistory();
      return false;
    }
  }

  async function cacheCurrentResult() {
    const currentId = state.resultId;
    const tracks = state.tracks.filter((track) => track.result).map((track) => ({ name: track.result.fileName, blob: track.result.blob, duration: track.result.duration, sampleRate: track.result.sampleRate, bitDepth: track.result.bitDepth, channels: track.result.channels }));
    if (!tracks.length) return;
    const size = tracks.reduce((sum, track) => sum + track.blob.size, 0);
    if (size > HISTORY_BYTES) {
      notice('Este resultado supera los 50 MiB del historial. Puedes descargarlo durante esta sesión; no se guardará para después de recargar la página.');
      return;
    }
    state.cachePending += 1;
    setControls();
    try {
      if (!state.db) state.db = await openDatabase();
      const records = (await allRecords()).sort((a, b) => b.createdAt - a.createdAt);
      const keep = [];
      let total = size;
      for (const record of records) {
        if (record.id === currentId) continue;
        if (keep.length < HISTORY_LIMIT - 1 && total + Number(record.size || 0) <= HISTORY_BYTES) { keep.push(record.id); total += Number(record.size || 0); }
      }
      const record = { id: currentId, title: tracks.length === 1 ? tracks[0].name : `${tracks.length} pistas WAV`, createdAt: Date.now(), size, tracks };
      await new Promise((resolve, reject) => {
        const transaction = state.db.transaction('conversions', 'readwrite');
        const store = transaction.objectStore('conversions');
        for (const old of records) if (!keep.includes(old.id)) store.delete(old.id);
        store.put(record);
        transaction.oncomplete = resolve;
        transaction.onerror = () => reject(transaction.error);
        transaction.onabort = () => reject(transaction.error);
      });
      await loadHistory();
      if (state.resultId === currentId) notice('Guardado en el historial de este navegador. Puedes recuperar estas descargas después de recargar la página.');
    } catch {
      if (state.resultId === currentId) notice('No hay espacio o permiso para guardar este resultado en el navegador. Descárgalo ahora: estará disponible mientras mantengas esta página abierta.');
    } finally { state.cachePending -= 1; setControls(); }
  }

  function historyDate(value) {
    try { return new Intl.DateTimeFormat('es', { day: 'numeric', month: 'short', hour: '2-digit', minute: '2-digit' }).format(new Date(value)); } catch { return ''; }
  }

  function renderHistory() {
    const count = $('#history-count');
    count.textContent = String(state.history.length);
    count.hidden = !state.history.length;
    $('#clear-history').disabled = isBusy() || state.cachePending > 0 || !state.history.length;
    const list = $('#history-list');
    list.replaceChildren();
    if (!state.history.length) { list.append(el('p', 'history-empty', 'Aquí aparecerán las conversiones que este navegador pueda guardar. Ningún archivo se sube a un servidor.')); return; }
    for (const record of state.history) {
      const row = el('button', 'history-item');
      row.type = 'button';
      row.append(icon('music'));
      const body = el('span');
      body.append(el('span', 'history-job-title', record.title), el('span', 'history-job-meta', `WAV · ${historyDate(record.createdAt)} · ${mb(record.size)}`));
      row.append(body, icon('arrow'));
      row.addEventListener('click', () => restoreHistory(record));
      list.append(row);
    }
  }

  function restoreHistory(record) {
    if (isBusy()) return toast('Espera a que termine la conversión actual para abrir otra.');
    state.generation += 1;
    releaseURLs();
    state.resultId = record.id;
    state.tracks = record.tracks.map((saved) => ({ id: id(), name: saved.name, status: 'completed', url: objectURL(saved.blob), result: { blob: saved.blob, fileName: saved.name, duration: saved.duration, sampleRate: saved.sampleRate, bitDepth: saved.bitDepth, channels: saved.channels } }));
    $('#track-list').replaceChildren(...state.tracks.map(renderTrack));
    $('#results').hidden = false;
    showResultState();
    notice('Resultado recuperado del almacenamiento de este navegador. Las descargas están listas.');
    setControls();
    $('#results').scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('#results-title').focus({ preventScroll: true });
  }

  async function clearHistory() {
    if (isBusy() || state.cachePending > 0 || !state.db) return;
    try {
      await new Promise((resolve, reject) => {
        const transaction = state.db.transaction('conversions', 'readwrite');
        transaction.objectStore('conversions').clear();
        transaction.oncomplete = resolve;
        transaction.onerror = () => reject(transaction.error);
      });
      reset();
      state.history = [];
      renderHistory();
      toast('Historial y archivos guardados eliminados de este navegador.');
    } catch { toast('No se pudo borrar el historial. Cierra otras pestañas de Onda e inténtalo de nuevo.'); }
  }

  $('#source-files').addEventListener('change', (event) => addFiles(event.target.files));
  const dropZone = $('#drop-zone');
  for (const type of ['dragenter', 'dragover']) dropZone.addEventListener(type, (event) => { event.preventDefault(); if (!isBusy()) dropZone.classList.add('drag-over'); });
  for (const type of ['dragleave', 'drop']) dropZone.addEventListener(type, (event) => { event.preventDefault(); dropZone.classList.remove('drag-over'); });
  dropZone.addEventListener('drop', (event) => { if (event.dataTransfer?.files) addFiles(event.dataTransfer.files); });
  $('#demo-button').addEventListener('click', makeDemo);
  $('#converter-form').addEventListener('submit', convert);
  $('#cancel-conversion').addEventListener('click', () => { state.controller?.abort(); $('#cancel-conversion').disabled = true; $('#cancel-conversion').textContent = 'Cancelando…'; });
  $('#close-results').addEventListener('click', reset);
  $('#new-conversion').addEventListener('click', reset);
  $('#download-zip').addEventListener('click', downloadZip);
  $('#history-toggle').addEventListener('click', () => {
    const panel = $('#history-panel');
    panel.hidden = !panel.hidden;
    $('#history-toggle').setAttribute('aria-expanded', String(!panel.hidden));
    if (!panel.hidden) { panel.scrollIntoView({ behavior: 'smooth', block: 'start' }); $('#history-title').focus({ preventScroll: true }); }
  });
  $('#clear-history').addEventListener('click', clearHistory);
  window.addEventListener('pagehide', (event) => { if (!event.persisted) { state.controller?.abort(); releaseURLs(); state.db?.close(); } });

  if (!engine?.supported) {
    $('#service-notice').textContent = 'Este navegador no ofrece las funciones de audio necesarias. Abre la página en una versión reciente de Chrome, Edge, Firefox o Safari.';
    $('#service-notice').hidden = false;
  }
  setControls();
  loadHistory();
})();
