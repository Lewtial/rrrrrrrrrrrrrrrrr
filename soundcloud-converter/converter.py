"""Audio conversion and public SoundCloud retrieval with bounded network access."""
from __future__ import annotations

import json
import math
import os
from pathlib import Path
import re
import shutil
import ssl
import subprocess
from typing import Callable
from urllib import error, parse, request

MAX_AUDIO_SECONDS = 3 * 60 * 60
DEMUXERS = "wav,mp3,flac,ogg,aac,mov,aiff,asf,matroska,webm"
FORMATS = {"wav": "wav", "mp3": "mp3", "flac": "flac", "ogg": "ogg", "aac": "m4a"}
UPLOAD_EXTENSIONS = {".wav", ".mp3", ".flac", ".ogg", ".opus", ".aac", ".m4a", ".aiff", ".aif", ".wma", ".mp4", ".webm"}

try:
    import yt_dlp
    from yt_dlp.networking import Request, Response
    from yt_dlp.networking.exceptions import HTTPError, TransportError
    from yt_dlp.downloader.http import HttpFD
    from yt_dlp.downloader.hls import HlsFD
    from yt_dlp.extractor.soundcloud import SoundcloudIE
except ImportError:  # Local file conversion is still available.
    yt_dlp = None


class ConversionError(Exception):
    """A message safe to show in the UI."""


def validate_soundcloud_url(value: str) -> str:
    value = value.strip()
    try:
        parts = parse.urlsplit(value)
        host = (parts.hostname or "").lower()
        port = parts.port
    except ValueError as exc:
        raise ValueError("Introduce un enlace válido de SoundCloud.") from exc
    if (parts.scheme != "https" or parts.username is not None or parts.password is not None or port is not None
            or host not in {"soundcloud.com", "www.soundcloud.com", "m.soundcloud.com", "on.soundcloud.com"}
            or not parts.path.strip("/") or "\\" in value or len(value) > 2048
            or any(ord(char) < 33 or ord(char) == 127 for char in value)):
        raise ValueError("Usa un enlace HTTPS de una pista o playlist pública de SoundCloud.")
    return parse.urlunsplit(("https", parts.netloc.lower(), parts.path, parts.query, ""))


def validate_provider_url(value: str) -> str:
    """Every provider request and redirect must stay on SoundCloud's HTTPS hosts."""
    try:
        parts = parse.urlsplit(value)
        host = (parts.hostname or "").lower().rstrip(".")
        port = parts.port
    except ValueError as exc:
        raise ConversionError("SoundCloud devolvió una dirección de audio no válida.") from exc
    if (parts.scheme != "https" or port not in {None, 443} or parts.username is not None or parts.password is not None
            or "\\" in value or any(ord(char) < 33 or ord(char) == 127 for char in value)
            or not (host == "soundcloud.com" or host.endswith(".soundcloud.com")
                    or host == "sndcdn.com" or host.endswith(".sndcdn.com"))):
        raise ConversionError("La dirección de descarga no pertenece a SoundCloud.")
    return value


class _SafeRedirect(request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        validate_provider_url(newurl)
        return super().redirect_request(req, fp, code, msg, headers, newurl)


class _QuietLogger:
    def debug(self, *_args, **_kwargs):
        pass

    warning = debug
    error = debug


if yt_dlp is not None:
    class SoundCloudDownloader(yt_dlp.YoutubeDL):
        """Use inherited HTTPS proxy/trust and validate even HTTP redirects."""
        def __init__(self, options):
            super().__init__(options)
            # create_default_context respects SSL_CERT_FILE supplied by the host.
            self._safe_opener = request.build_opener(
                request.ProxyHandler(), _SafeRedirect(),
                request.HTTPSHandler(context=ssl.create_default_context()),
            )

        def urlopen(self, req):
            if isinstance(req, str):
                req = Request(req)
            validate_provider_url(req.url)
            headers = dict(req.headers)
            # urllib does not transparently decompress yt-dlp's encoding requests.
            headers["Accept-Encoding"] = "identity"
            raw_request = request.Request(req.url, data=req.data, headers=headers, method=req.method)
            try:
                raw = self._safe_opener.open(raw_request, timeout=25)
                validate_provider_url(raw.url)
                return Response(raw, raw.url, dict(raw.headers), status=raw.status, reason=raw.reason)
            except error.HTTPError as exc:
                raise HTTPError(Response(exc, exc.url, dict(exc.headers), status=exc.code, reason=exc.reason)) from exc
            except (error.URLError, TimeoutError, OSError) as exc:
                raise TransportError("No se pudo conectar a SoundCloud.", cause=exc) from exc

        def dl(self, name, info, subtitle=False, test=False):
            """Never allow a remote URL to reach an external/FFmpeg downloader."""
            protocol = info.get("protocol") or "https"
            validate_provider_url(info["url"])
            info = self._copy_infodict(info)
            if protocol in {"http", "https"}:
                downloader_class = HttpFD
            elif protocol == "m3u8_native":
                manifest = info.get("hls_media_playlist_data")
                if not manifest:
                    with self.urlopen(info["url"]) as response:
                        content = response.read(2 * 1024 * 1024 + 1)
                        if len(content) > 2 * 1024 * 1024:
                            raise ConversionError("La lista de audio de SoundCloud es demasiado grande.")
                        manifest = content.decode("utf-8", "replace")
                        info["url"] = response.url
                if (not HlsFD.can_download(manifest, info, False)
                        or re.search(r"#EXT-X-KEY:.*METHOD=(?!NONE(?:,|$))", manifest)):
                    raise ConversionError("Esta transmisión usa un formato protegido o no compatible.")
                # HlsFD will use this already-checked manifest and cannot fall
                # back to FFmpeg for unsupported features or encrypted streams.
                info["hls_media_playlist_data"] = manifest
                downloader_class = HlsFD
            else:
                raise ConversionError("El formato de transmisión de esta pista no es compatible.")
            if info.get("http_headers") is None:
                info["http_headers"] = self._calc_headers(info)
            downloader = downloader_class(self, self.params)
            for hook in self._progress_hooks:
                downloader.add_progress_hook(hook)
            return downloader.download(name, info, subtitle)


def validate_track_url(value: str) -> str:
    """Playlist entries can refer to SoundCloud's own numeric tracks API."""
    validate_provider_url(value)
    parsed = parse.urlsplit(value)
    if parsed.hostname in {"api.soundcloud.com", "api-v2.soundcloud.com"}:
        if not re.fullmatch(r"/tracks/\d+/?", parsed.path):
            raise ConversionError("La pista de la playlist no tiene una dirección válida.")
    else:
        validate_soundcloud_url(value)
    if yt_dlp is None or not SoundcloudIE.suitable(value):
        raise ConversionError("La playlist contiene una pista no compatible.")
    return value


def provider_available() -> bool:
    return yt_dlp is not None


def safe_title(value: str, fallback: str = "audio") -> str:
    cleaned = re.sub(r"[^\w .()-]", "_", str(value), flags=re.UNICODE).strip(" .")
    return cleaned[:100].rstrip(" .") or fallback


def probe_audio(source: Path) -> dict:
    if shutil.which("ffprobe") is None:
        raise ConversionError("Falta FFprobe en el servidor para comprobar el audio.")
    try:
        result = subprocess.run([
            "ffprobe", "-v", "error", "-protocol_whitelist", "file,pipe",
            "-format_whitelist", DEMUXERS,
            "-show_entries", "format=duration,format_name:stream=codec_type,sample_rate,channels",
            "-of", "json", str(source),
        ], capture_output=True, text=True, timeout=25, check=True)
        data = json.loads(result.stdout)
        stream = next(s for s in data.get("streams", []) if s.get("codec_type") == "audio")
        duration = float(data.get("format", {}).get("duration", 0))
        if not math.isfinite(duration) or duration < 0 or duration > MAX_AUDIO_SECONDS:
            raise ConversionError("El audio supera la duración máxima de tres horas.")
        return {"duration": round(duration, 2), "sample_rate": int(stream.get("sample_rate", 0)),
                "channels": int(stream.get("channels", 0)), "source_format": data["format"].get("format_name", "")}
    except ConversionError:
        raise
    except (subprocess.SubprocessError, ValueError, KeyError, StopIteration) as exc:
        raise ConversionError("No se pudo leer el archivo. Comprueba que sea un audio válido.") from exc


def convert_audio(source: Path, destination: Path, options: dict) -> dict:
    info = probe_audio(source)
    command = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-nostdin", "-y",
               "-threads", "1", "-filter_threads", "1", "-protocol_whitelist", "file,pipe",
               "-format_whitelist", DEMUXERS, "-i", str(source), "-map", "0:a:0", "-vn",
               "-map_metadata", "-1", "-t", str(MAX_AUDIO_SECONDS)]
    if options["normalize"]:
        command += ["-af", "loudnorm=I=-14:TP=-1:LRA=11"]
    command += ["-ar", str(options["sample_rate"]), "-ac", "2"]
    bits = options["bit_depth"]
    codec = {
        "wav": ["-c:a", "pcm_s24le" if bits == 24 else "pcm_s16le"],
        "mp3": ["-c:a", "libmp3lame", "-b:a", "320k"],
        "flac": ["-c:a", "flac", "-compression_level", "8", "-sample_fmt", "s32" if bits == 24 else "s16", "-bits_per_raw_sample", str(bits)],
        "ogg": ["-c:a", "libvorbis", "-b:a", "320k"],
        "aac": ["-c:a", "aac", "-b:a", "320k", "-movflags", "+faststart"],
    }[options["format"]]
    command += codec + [str(destination)]
    try:
        subprocess.run(command, capture_output=True, timeout=min(1200, max(60, info["duration"] * 3 + 30)), check=True)
        if not destination.is_file() or destination.stat().st_size < 32:
            raise ConversionError("La conversión no generó un archivo de audio válido.")
        return info
    except (subprocess.SubprocessError, OSError) as exc:
        destination.unlink(missing_ok=True)
        raise ConversionError("No se pudo convertir el audio. Prueba con otro archivo o formato.") from exc


def _options(max_tracks: int, max_bytes: int, progress: Callable | None = None) -> dict:
    def hook(state):
        downloaded = state.get("downloaded_bytes", 0)
        if downloaded > max_bytes:
            raise ConversionError("La pista supera el tamaño máximo permitido.")
        if progress and state.get("status") == "downloading":
            total = state.get("total_bytes") or state.get("total_bytes_estimate")
            if total:
                progress(min(49, int(downloaded / total * 49)))

    return {"quiet": True, "no_warnings": True, "logger": _QuietLogger(),
            "format": "bestaudio/best", "extract_flat": "in_playlist",
            "allowed_extractors": ["^soundcloud$", "^soundcloud:set$", "^soundcloud:playlist$"],
            "playlistend": max_tracks, "noplaylist": False, "socket_timeout": 25,
            "retries": 1, "fragment_retries": 1, "hls_prefer_native": True,
            "concurrent_fragment_downloads": 1, "max_filesize": max_bytes,
            "fixup": "never", "postprocessors": [], "progress_hooks": [hook],
            "cachedir": False, "writeinfojson": False, "writethumbnail": False}


def discover_soundcloud(url: str, limit: int, max_bytes: int) -> list[dict]:
    if yt_dlp is None:
        raise ConversionError("Falta el componente de SoundCloud en el servidor. Puedes convertir archivos locales.")
    try:
        with SoundCloudDownloader(_options(limit, max_bytes)) as downloader:
            url = validate_soundcloud_url(url)
            if parse.urlsplit(url).hostname == "on.soundcloud.com":
                # Resolve the approved shortlink through the same redirect guard;
                # do not enable yt-dlp's generic URL extractor.
                with downloader.urlopen(url) as response:
                    url = validate_soundcloud_url(response.url)
            info = downloader.extract_info(url, download=False)
            if not info:
                raise ConversionError("No se encontraron pistas públicas en este enlace.")
            entries = info.get("entries")
            if entries is None:
                return [info]
            result = []
            for entry in entries:
                if entry:
                    result.append(entry)
                if len(result) >= limit:
                    break
            if not result:
                raise ConversionError("No se encontraron pistas públicas en este enlace.")
            return result
    except ConversionError:
        raise
    except Exception as exc:
        raise provider_error(exc) from exc


def download_soundcloud(info: dict, directory: Path, max_bytes: int, progress: Callable) -> tuple[Path, dict]:
    try:
        options = _options(1, max_bytes, progress)
        options.update({"extract_flat": False, "outtmpl": str(directory / "source.%(ext)s"), "noplaylist": True})
        with SoundCloudDownloader(options) as downloader:
            if info.get("_type") in {"url", "url_transparent"} or not info.get("url"):
                track_url = validate_track_url(info.get("webpage_url") or info.get("url") or "")
                info = downloader.extract_info(track_url, download=False)
            if not info or info.get("entries") is not None:
                raise ConversionError("Este enlace no corresponde a una pista individual.")
            if info.get("availability") in {"private", "premium_only", "subscriber_only", "needs_auth"}:
                raise ConversionError("La pista requiere acceso privado o de pago y no se puede procesar.")
            if info.get("duration", 0) and info["duration"] > MAX_AUDIO_SECONDS:
                raise ConversionError("La pista supera la duración máxima de tres horas.")
            if info.get("is_live"):
                raise ConversionError("No se pueden convertir transmisiones en directo.")
            if (info.get("is_preview") or info.get("snipped")
                    or "preview" in str(info.get("format_id", "")).lower()
                    or "/preview/" in (info.get("url") or "")
                    or re.search(r"/(?:preview|playlist)/0/30/", info.get("url") or "")):
                raise ConversionError("SoundCloud solo ofrece una vista previa de esta pista. No se puede descargar la canción completa.")
            validate_provider_url(info.get("url") or "")
            # Only yt-dlp's native HTTP/HLS downloaders are permitted. The
            # downloader's urlopen guard applies to every manifest and segment.
            if info.get("protocol") not in {None, "http", "https", "m3u8_native"}:
                raise ConversionError("El formato de transmisión de esta pista no es compatible.")
            downloader.process_info(info)
            candidates = [p for p in directory.glob("source.*") if p.is_file() and p.suffix not in {".part", ".ytdl"}]
            if not candidates:
                raise ConversionError("No se recibió el audio de SoundCloud.")
            source = max(candidates, key=lambda p: p.stat().st_size)
            if source.stat().st_size > max_bytes:
                raise ConversionError("La pista supera el tamaño máximo permitido.")
            return source, info
    except ConversionError:
        raise
    except Exception as exc:
        raise provider_error(exc) from exc


def provider_error(exc: Exception) -> ConversionError:
    text = str(exc).lower()
    if any(word in text for word in ("403", "forbidden", "tunnel", "proxy", "connect", "network")):
        return ConversionError("No se pudo acceder a SoundCloud. El servidor puede tener restricciones de red o la pista puede restringir su descarga. Puedes subir un archivo de audio.")
    if any(word in text for word in ("private", "premium", "login", "sign in", "subscriber")):
        return ConversionError("La pista requiere acceso privado o de pago y no se puede procesar.")
    if "404" in text or "not available" in text:
        return ConversionError("La pista no está disponible públicamente. Comprueba el enlace.")
    return ConversionError("No se pudo descargar esta pista. Comprueba que sea pública y vuelve a intentarlo.")
