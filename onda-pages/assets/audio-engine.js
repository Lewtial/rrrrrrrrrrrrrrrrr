(function () {
  "use strict";

  var AudioContextType = window.AudioContext || window.webkitAudioContext;
  var OfflineContextType = window.OfflineAudioContext || window.webkitOfflineAudioContext;
  var limits = Object.freeze({
    maxFileBytes: 25 * 1024 * 1024,
    maxFiles: 10,
    maxTotalInputBytes: 100 * 1024 * 1024,
    maxOutputBytes: 200 * 1024 * 1024,
    maxDuration: 600
  });
  var supported = !!(AudioContextType && OfflineContextType && window.Worker && window.Blob &&
    window.FileReader && window.TextEncoder && window.URL && window.URL.createObjectURL);

  function abortError() {
    try { return new DOMException("La conversión se canceló.", "AbortError"); }
    catch (_) { var error = new Error("La conversión se canceló."); error.name = "AbortError"; return error; }
  }

  function checkAbort(signal) {
    if (signal && signal.aborted) throw abortError();
  }

  function report(callback, progress, stage) {
    if (typeof callback !== "function") return;
    // A presentation callback must not leave a worker or decoder orphaned.
    try { callback({ progress: Math.max(0, Math.min(100, Math.round(progress))), stage: stage }); }
    catch (_) { /* Conversion lifetime is independent from UI callbacks. */ }
  }

  function cleanName(value, fallback) {
    var name = String(value || "").split(/[\\/]/).pop();
    if (name.normalize) name = name.normalize("NFC");
    name = name.replace(/[\u0000-\u001f\u007f<>:"/\\|?*]/g, "_")
      .replace(/^[.\s]+|[.\s]+$/g, "");
    name = Array.from(name).slice(0, 120).join("");
    if (!name) name = fallback || "audio";
    if (/^(con|prn|aux|nul|com[1-9]|lpt[1-9])(?:\.|$)/i.test(name)) name = "_" + name;
    return name;
  }

  function waveName(original) {
    var name = cleanName(original, "audio").replace(/\.[^.]+$/, "");
    return cleanName(name, "audio") + ".wav";
  }

  function metadata(file, signal) {
    return new Promise(function (resolve, reject) {
      checkAbort(signal);
      var audio = document.createElement("audio");
      var url = URL.createObjectURL(file);
      var done = false;
      var timer;
      function finish(error, duration) {
        if (done) return;
        done = true;
        clearTimeout(timer);
        audio.onloadedmetadata = null;
        audio.onerror = null;
        if (signal) signal.removeEventListener("abort", cancel);
        audio.removeAttribute("src");
        try { audio.load(); } catch (_) { /* Resource release is best effort. */ }
        URL.revokeObjectURL(url);
        if (error) reject(error); else resolve(duration);
      }
      function cancel() { finish(abortError()); }
      audio.preload = "metadata";
      audio.onloadedmetadata = function () {
        var duration = audio.duration;
        if (Number.isFinite(duration) && duration > limits.maxDuration) {
          finish(new Error("El audio supera los 10 minutos. Selecciona un archivo más corto."));
        } else {
          finish(null, Number.isFinite(duration) && duration > 0 ? duration : null);
        }
      };
      audio.onerror = function () {
        finish(new Error("El navegador no reconoce este audio. Prueba con un archivo WAV, MP3, M4A u OGG compatible."));
      };
      if (signal) signal.addEventListener("abort", cancel, { once: true });
      timer = setTimeout(function () {
        finish(new Error("No se pudo leer el audio. Comprueba que el archivo esté completo y use un formato compatible."));
      }, 12000);
      audio.src = url;
    });
  }

  function readFile(file, signal, callback) {
    return new Promise(function (resolve, reject) {
      checkAbort(signal);
      var reader = new FileReader();
      function cleanup() {
        reader.onload = reader.onerror = reader.onabort = reader.onprogress = null;
        if (signal) signal.removeEventListener("abort", cancel);
      }
      function cancel() { reader.abort(); }
      reader.onload = function () { var result = reader.result; cleanup(); resolve(result); };
      reader.onerror = function () { cleanup(); reject(new Error("No se pudo leer el archivo seleccionado.")); };
      reader.onabort = function () { cleanup(); reject(abortError()); };
      reader.onprogress = function (event) {
        if (event.lengthComputable) report(callback, 5 + event.loaded / event.total * 10, "Leyendo archivo");
      };
      if (signal) signal.addEventListener("abort", cancel, { once: true });
      reader.readAsArrayBuffer(file);
    });
  }

  function abortable(promise, signal, onAbort) {
    if (!signal) return promise;
    return new Promise(function (resolve, reject) {
      var settled = false;
      function cancel() {
        if (settled) return;
        settled = true;
        signal.removeEventListener("abort", cancel);
        if (onAbort) { try { onAbort(); } catch (_) { /* Already stopped. */ } }
        reject(abortError());
      }
      if (signal.aborted) { cancel(); return; }
      signal.addEventListener("abort", cancel, { once: true });
      promise.then(function (value) {
        if (settled) return;
        settled = true;
        signal.removeEventListener("abort", cancel);
        resolve(value);
      }, function (error) {
        if (settled) return;
        settled = true;
        signal.removeEventListener("abort", cancel);
        reject(error);
      });
    });
  }

  function closeContext(context) {
    if (!context || typeof context.close !== "function" || context.state === "closed") return;
    try {
      var result = context.close();
      if (result && typeof result.catch === "function") result.catch(function () {});
    } catch (_) { /* Old WebKit can throw for an already closed context. */ }
  }

  function decode(context, bytes) {
    // Both the callback-based WebKit API and current Promise API are supported.
    return new Promise(function (resolve, reject) {
      var completed = false;
      function success(value) { if (!completed) { completed = true; resolve(value); } }
      function failure(error) { if (!completed) { completed = true; reject(error); } }
      try {
        var result = context.decodeAudioData(bytes, success, failure);
        if (result && typeof result.then === "function") result.then(success, failure);
      } catch (error) { failure(error); }
    });
  }

  function pcmWorkerMain() {
    "use strict";
    self.onmessage = function (event) {
      try {
        var data = event.data;
        var left = new Float32Array(data.left);
        var right = new Float32Array(data.right);
        var frames = left.length;
        var bytesPerSample = data.bitDepth / 8;
        var dataBytes = frames * 2 * bytesPerSample;
        var totalBytes = 44 + dataBytes;
        if (!frames || right.length !== frames || !Number.isSafeInteger(totalBytes) || totalBytes > data.maxOutputBytes) {
          throw new Error("El WAV supera el espacio disponible para este lote.");
        }
        var lastProgress = -1;
        function progress(value, stage) {
          var rounded = Math.floor(value);
          if (rounded !== lastProgress) {
            lastProgress = rounded;
            self.postMessage({ type: "progress", progress: rounded, stage: stage });
          }
        }
        var gain = 1;
        var frame;
        if (data.normalize) {
          var peak = 0;
          for (frame = 0; frame < frames; frame++) {
            var a = Number.isFinite(left[frame]) ? Math.abs(left[frame]) : 0;
            var b = Number.isFinite(right[frame]) ? Math.abs(right[frame]) : 0;
            if (a > peak) peak = a;
            if (b > peak) peak = b;
            if ((frame & 65535) === 0) progress(frame / frames * 35, "Analizando picos");
          }
          if (peak > 0) gain = Math.pow(10, -1 / 20) / peak;
          progress(35, "Normalizando a −1 dBFS");
        }
        var output = new ArrayBuffer(totalBytes);
        var view = new DataView(output);
        function text(offset, value) {
          for (var i = 0; i < value.length; i++) view.setUint8(offset + i, value.charCodeAt(i));
        }
        text(0, "RIFF");
        view.setUint32(4, totalBytes - 8, true);
        text(8, "WAVE");
        text(12, "fmt ");
        view.setUint32(16, 16, true);
        view.setUint16(20, 1, true);
        view.setUint16(22, 2, true);
        view.setUint32(24, data.sampleRate, true);
        view.setUint32(28, data.sampleRate * 2 * bytesPerSample, true);
        view.setUint16(32, 2 * bytesPerSample, true);
        view.setUint16(34, data.bitDepth, true);
        text(36, "data");
        view.setUint32(40, dataBytes, true);
        var position = 44;
        var base = data.normalize ? 35 : 0;
        var scale = data.normalize ? 65 : 100;
        for (frame = 0; frame < frames; frame++) {
          for (var channel = 0; channel < 2; channel++) {
            var sample = channel ? right[frame] : left[frame];
            sample = Number.isFinite(sample) ? Math.max(-1, Math.min(1, sample * gain)) : 0;
            if (data.bitDepth === 16) {
              var pcm16 = Math.round(sample * (sample < 0 ? 32768 : 32767));
              view.setInt16(position, pcm16, true);
              position += 2;
            } else {
              var pcm24 = Math.round(sample * (sample < 0 ? 8388608 : 8388607));
              view.setUint8(position, pcm24 & 255);
              view.setUint8(position + 1, (pcm24 >> 8) & 255);
              view.setUint8(position + 2, (pcm24 >> 16) & 255);
              position += 3;
            }
          }
          if ((frame & 65535) === 0) progress(base + frame / frames * scale, "Codificando WAV");
        }
        progress(100, "WAV codificado");
        self.postMessage({ type: "complete", buffer: output }, [output]);
      } catch (error) {
        self.postMessage({ type: "error", message: error && error.message ? error.message : "No se pudo codificar el WAV." });
      }
    };
  }

  function encodeWave(left, right, options, callback, signal) {
    return new Promise(function (resolve, reject) {
      checkAbort(signal);
      var url = URL.createObjectURL(new Blob(["(", pcmWorkerMain.toString(), ")();"], { type: "text/javascript" }));
      var worker;
      var settled = false;
      function cleanup() {
        if (signal) signal.removeEventListener("abort", cancel);
        if (worker) {
          worker.onmessage = worker.onerror = worker.onmessageerror = null;
          worker.terminate();
        }
        URL.revokeObjectURL(url);
      }
      function finish(error, result) {
        if (settled) return;
        settled = true;
        cleanup();
        if (error) reject(error); else resolve(result);
      }
      function cancel() { finish(abortError()); }
      try {
        worker = new Worker(url);
        worker.onmessage = function (event) {
          var data = event.data || {};
          if (data.type === "progress") report(callback, 65 + data.progress * .34, data.stage);
          else if (data.type === "complete") finish(null, new Blob([data.buffer], { type: "audio/wav" }));
          else if (data.type === "error") finish(new Error(data.message || "No se pudo codificar el WAV."));
        };
        worker.onerror = function () { finish(new Error("No se pudo iniciar la conversión en este navegador.")); };
        worker.onmessageerror = function () { finish(new Error("No se pudo recibir el audio convertido.")); };
        if (signal) signal.addEventListener("abort", cancel, { once: true });
        checkAbort(signal);
        worker.postMessage({ left: left.buffer, right: right.buffer, sampleRate: options.sampleRate,
          bitDepth: options.bitDepth, normalize: options.normalize, maxOutputBytes: options.maxOutputBytes },
        [left.buffer, right.buffer]);
      } catch (error) { finish(error); }
    });
  }

  async function convert(file, options, onProgress, signal) {
    checkAbort(signal);
    if (!supported) throw new Error("Este navegador no dispone de conversión de audio. Prueba con una versión reciente de Chrome, Edge, Firefox o Safari.");
    if (!(file instanceof Blob) || !Number.isFinite(file.size) || file.size < 1) throw new Error("Selecciona un archivo de audio que no esté vacío.");
    if (file.size > limits.maxFileBytes) throw new Error("Cada archivo puede ocupar como máximo 25 MiB.");
    options = options || {};
    var sampleRate = options.sampleRate === undefined ? 44100 : Number(options.sampleRate);
    var bitDepth = options.bitDepth === undefined ? 16 : Number(options.bitDepth);
    var maxOutputBytes = options.maxOutputBytes === undefined ? limits.maxOutputBytes : Math.floor(Number(options.maxOutputBytes));
    if (sampleRate !== 44100 && sampleRate !== 48000) throw new Error("Selecciona una frecuencia de 44,1 o 48 kHz.");
    if (bitDepth !== 16 && bitDepth !== 24) throw new Error("Selecciona una profundidad de 16 o 24 bits.");
    if (!Number.isFinite(maxOutputBytes) || maxOutputBytes < 44) throw new Error("No queda espacio disponible para el WAV en este lote.");
    maxOutputBytes = Math.min(maxOutputBytes, limits.maxOutputBytes);
    var configuration = { sampleRate: sampleRate, bitDepth: bitDepth, normalize: !!options.normalize, maxOutputBytes: maxOutputBytes };
    var bytesPerFrame = 2 * (bitDepth / 8);
    function checkDuration(duration) {
      if (!Number.isFinite(duration) || duration <= 0) throw new Error("El archivo no contiene una duración de audio válida.");
      if (duration > limits.maxDuration) throw new Error("El audio supera los 10 minutos. Selecciona un archivo más corto.");
      var frames = Math.ceil(duration * sampleRate);
      if (44 + frames * bytesPerFrame > maxOutputBytes) throw new Error("El WAV supera el espacio disponible para este lote. Elige 16 bits o divide los archivos en lotes.");
      return frames;
    }
    report(onProgress, 0, "Comprobando audio");
    var originalDuration = await metadata(file, signal);
    checkAbort(signal);
    if (originalDuration !== null) checkDuration(originalDuration);
    report(onProgress, 5, "Leyendo archivo");
    var input = await readFile(file, signal, onProgress);
    checkAbort(signal);
    var context;
    var decoded;
    try {
      try { context = new AudioContextType({ sampleRate: sampleRate }); }
      catch (_) { context = new AudioContextType(); }
      report(onProgress, 20, "Decodificando audio");
      try {
        decoded = await abortable(decode(context, input), signal, function () { closeContext(context); });
      } catch (error) {
        if (error && error.name === "AbortError") throw error;
        throw new Error("El navegador no puede decodificar este archivo. El códec puede no ser compatible o el audio puede estar dañado.");
      }
    } finally {
      input = null;
      closeContext(context);
    }
    checkAbort(signal);
    var frames = checkDuration(decoded.duration);
    report(onProgress, 40, "Preparando audio estéreo");
    var offline = new OfflineContextType(2, frames, sampleRate);
    var source = offline.createBufferSource();
    source.buffer = decoded;
    source.channelInterpretation = "speakers";
    source.connect(offline.destination);
    source.start(0);
    var stereo;
    try {
      report(onProgress, 45, "Ajustando frecuencia y canales");
      stereo = await abortable(offline.startRendering(), signal, function () {
        try { source.stop(); source.disconnect(); } catch (_) { /* Already rendered. */ }
      });
    } catch (error) {
      if (error && error.name === "AbortError") throw error;
      throw new Error("No se pudo preparar el audio estéreo. Prueba con un archivo más corto.");
    } finally {
      try { source.disconnect(); } catch (_) { /* Already disconnected. */ }
      source.buffer = null;
      source = null;
      decoded = null;
      offline = null;
    }
    checkAbort(signal);
    report(onProgress, 60, "Preparando WAV");
    var duration = stereo.length / stereo.sampleRate;
    // Transfer independent channel copies: AudioBuffer storage is browser-owned.
    var left = new Float32Array(stereo.getChannelData(0));
    var right = new Float32Array(stereo.getChannelData(1));
    stereo = null;
    report(onProgress, 65, configuration.normalize ? "Analizando picos" : "Codificando WAV");
    var blob = await encodeWave(left, right, configuration, onProgress, signal);
    left = right = null;
    checkAbort(signal);
    report(onProgress, 100, "Listo para descargar");
    return { blob: blob, fileName: waveName(file.name), duration: duration,
      sampleRate: sampleRate, bitDepth: bitDepth, channels: 2 };
  }

  var crcTable;
  function getCrcTable() {
    if (crcTable) return crcTable;
    crcTable = new Uint32Array(256);
    for (var n = 0; n < 256; n++) {
      var c = n;
      for (var k = 0; k < 8; k++) c = c & 1 ? 0xedb88320 ^ (c >>> 1) : c >>> 1;
      crcTable[n] = c >>> 0;
    }
    return crcTable;
  }

  async function blobCrc(blob, consumed, total, callback) {
    var table = getCrcTable();
    var crc = 0xffffffff;
    var processed = 0;
    var sinceYield = 0;
    // Slice reads cap transient memory even for a 200 MiB result.
    while (processed < blob.size) {
      var buffer = await blob.slice(processed, Math.min(blob.size, processed + 256 * 1024)).arrayBuffer();
      var bytes = new Uint8Array(buffer);
      for (var i = 0; i < bytes.length; i++) crc = table[(crc ^ bytes[i]) & 255] ^ (crc >>> 8);
      processed += bytes.length;
      sinceYield += bytes.length;
      report(callback, total ? (consumed + processed) / total * 95 : 95, "Preparando descarga ZIP");
      if (sinceYield >= 2 * 1024 * 1024) {
        sinceYield = 0;
        await new Promise(function (resolve) { setTimeout(resolve, 0); });
      }
    }
    return (crc ^ 0xffffffff) >>> 0;
  }

  function uniqueName(original, used) {
    var name = cleanName(original, "audio.wav");
    var initial = name;
    var dot = initial.lastIndexOf(".");
    var stem = dot > 0 ? initial.slice(0, dot) : initial;
    var extension = dot > 0 ? initial.slice(dot) : "";
    var index = 2;
    while (used.has(name.toLowerCase())) { name = stem + " (" + index++ + ")" + extension; }
    used.add(name.toLowerCase());
    return name;
  }

  async function createZip(files, onProgress) {
    if (!Array.isArray(files) || !files.length) throw new Error("No hay archivos convertidos para descargar.");
    if (files.length > limits.maxFiles) throw new Error("Cada ZIP puede contener como máximo 10 archivos.");
    var total = 0;
    files.forEach(function (file) {
      if (!file || !(file.blob instanceof Blob)) throw new Error("Uno de los archivos del ZIP no es válido.");
      total += file.blob.size;
    });
    if (total > limits.maxOutputBytes) throw new Error("Los archivos superan los 200 MiB permitidos por lote.");
    var encoder = new TextEncoder();
    var used = new Set();
    var localParts = [];
    var centralParts = [];
    var offset = 0;
    var centralSize = 0;
    var consumed = 0;
    var date = new Date();
    var dosTime = (date.getHours() << 11) | (date.getMinutes() << 5) | Math.floor(date.getSeconds() / 2);
    var dosDate = ((Math.max(1980, Math.min(2107, date.getFullYear())) - 1980) << 9) | ((date.getMonth() + 1) << 5) | date.getDate();
    report(onProgress, 0, "Preparando descarga ZIP");
    for (var index = 0; index < files.length; index++) {
      var file = files[index];
      var name = encoder.encode(uniqueName(file.name, used));
      var crc = await blobCrc(file.blob, consumed, total, onProgress);
      consumed += file.blob.size;
      var local = new Uint8Array(30 + name.length);
      var header = new DataView(local.buffer);
      header.setUint32(0, 0x04034b50, true);
      header.setUint16(4, 20, true);
      header.setUint16(6, 0x0800, true); // UTF-8 file names.
      header.setUint16(8, 0, true); // Store: payloads are already WAV.
      header.setUint16(10, dosTime, true);
      header.setUint16(12, dosDate, true);
      header.setUint32(14, crc, true);
      header.setUint32(18, file.blob.size, true);
      header.setUint32(22, file.blob.size, true);
      header.setUint16(26, name.length, true);
      header.setUint16(28, 0, true);
      local.set(name, 30);
      localParts.push(local, file.blob);
      var central = new Uint8Array(46 + name.length);
      var directory = new DataView(central.buffer);
      directory.setUint32(0, 0x02014b50, true);
      directory.setUint16(4, 20, true);
      directory.setUint16(6, 20, true);
      directory.setUint16(8, 0x0800, true);
      directory.setUint16(10, 0, true);
      directory.setUint16(12, dosTime, true);
      directory.setUint16(14, dosDate, true);
      directory.setUint32(16, crc, true);
      directory.setUint32(20, file.blob.size, true);
      directory.setUint32(24, file.blob.size, true);
      directory.setUint16(28, name.length, true);
      directory.setUint16(30, 0, true);
      directory.setUint16(32, 0, true);
      directory.setUint16(34, 0, true);
      directory.setUint16(36, 0, true);
      directory.setUint32(38, 0, true);
      directory.setUint32(42, offset, true);
      central.set(name, 46);
      centralParts.push(central);
      centralSize += central.length;
      offset += local.length + file.blob.size;
    }
    var end = new Uint8Array(22);
    var endView = new DataView(end.buffer);
    endView.setUint32(0, 0x06054b50, true);
    endView.setUint16(4, 0, true);
    endView.setUint16(6, 0, true);
    endView.setUint16(8, files.length, true);
    endView.setUint16(10, files.length, true);
    endView.setUint32(12, centralSize, true);
    endView.setUint32(16, offset, true);
    endView.setUint16(20, 0, true);
    var result = new Blob(localParts.concat(centralParts, [end]), { type: "application/zip" });
    report(onProgress, 100, "ZIP listo para descargar");
    return result;
  }

  window.OndaAudio = Object.freeze({ convert: convert, createZip: createZip, supported: supported, limits: limits });
})();
