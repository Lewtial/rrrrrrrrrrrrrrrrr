"""Onda: a self-hosted audio converter, without subscriptions or accounts."""
from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
import asyncio
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import shutil
import threading
import time
from typing import Literal
from uuid import UUID, uuid4
import zipfile

from fastapi import FastAPI, File, Form, HTTPException, UploadFile
from fastapi.exceptions import RequestValidationError
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator
from starlette.formparsers import MultiPartException

from converter import (ConversionError, FORMATS, UPLOAD_EXTENSIONS, convert_audio,
                       discover_soundcloud, download_soundcloud, provider_available,
                       safe_title, validate_soundcloud_url)

BASE_DIR = Path(__file__).resolve().parent
MAX_UPLOAD_BYTES = max(1, int(os.getenv("ONDA_MAX_UPLOAD_MB", "200"))) * 1024 * 1024
MAX_TRACKS = max(1, min(200, int(os.getenv("ONDA_MAX_PLAYLIST_TRACKS", "50"))))
JOB_TTL = max(1, float(os.getenv("ONDA_JOB_TTL_HOURS", "24"))) * 3600
MAX_WORKERS = max(1, min(8, int(os.getenv("ONDA_MAX_WORKERS", "2"))))
MAX_PENDING_JOBS = MAX_WORKERS * 4


class BodyLimitMiddleware:
    """Bound request bodies before Starlette spools multipart uploads."""
    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        if scope["type"] != "http" or scope.get("method") != "POST":
            return await self.app(scope, receive, send)
        limit = MAX_UPLOAD_BYTES * 2 + 2 * 1024 * 1024 if scope.get("path") == "/api/uploads" else 512 * 1024
        message = "La petición supera el tamaño máximo permitido. Divide el lote en archivos más pequeños."
        headers = dict(scope.get("headers", []))
        try:
            content_length = int(headers.get(b"content-length", b"0"))
        except ValueError:
            return await JSONResponse({"detail": "El tamaño de la petición no es válido."}, status_code=400)(scope, receive, send)
        if content_length < 0 or content_length > limit:
            return await JSONResponse({"detail": message}, status_code=413)(scope, receive, send)
        received = 0
        exceeded = False
        replacement = json.dumps({"detail": message}, ensure_ascii=False).encode()

        async def limited_receive():
            nonlocal received, exceeded
            event = await receive()
            if event["type"] == "http.request":
                received += len(event.get("body", b""))
                if received > limit:
                    exceeded = True
                    # MultiPartParser closes its temporary files on this exact
                    # exception type before the standard handler returns 400.
                    raise MultiPartException(message)
            return event

        async def limited_send(event):
            if exceeded and event["type"] == "http.response.start":
                event = {**event, "status": 413, "headers": [
                    (b"content-type", b"application/json"), (b"content-length", str(len(replacement)).encode())]}
            elif exceeded and event["type"] == "http.response.body":
                event = {"type": "http.response.body", "body": replacement, "more_body": False}
            await send(event)

        await self.app(scope, limited_receive, limited_send)


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def valid_id(value: str) -> bool:
    try:
        return str(UUID(value)) == value
    except (ValueError, AttributeError):
        return False


class ConversionOptions(BaseModel):
    model_config = ConfigDict(extra="forbid")
    format: Literal["wav", "mp3", "flac", "ogg", "aac"] = "wav"
    sample_rate: Literal[44100, 48000] = 44100
    bit_depth: Literal[16, 24] = 16
    normalize: bool = False


class URLJob(ConversionOptions):
    urls: list[str] = Field(min_length=1, max_length=20)

    @field_validator("urls")
    @classmethod
    def check_urls(cls, urls):
        return list(dict.fromkeys(validate_soundcloud_url(url) for url in urls))


class JobManager:
    def __init__(self, root: Path):
        self.root = root.resolve()
        self.root.mkdir(parents=True, exist_ok=True)
        self.lock = threading.RLock()
        self.jobs: dict[str, dict] = {}
        self.remote_sources: dict[str, dict] = {}
        self.executor = ThreadPoolExecutor(max_workers=MAX_WORKERS, thread_name_prefix="onda")
        self._load()
        self.cleanup()

    def _load(self):
        for path in self.root.iterdir():
            if not path.is_dir() or path.is_symlink() or not valid_id(path.name):
                continue
            try:
                job = json.loads((path / "job.json").read_text())
                if job["id"] != path.name or not isinstance(job.get("tracks"), list):
                    continue
                self.jobs[path.name] = job
                if job["status"] in {"queued", "processing"}:
                    for track in job["tracks"]:
                        if track["status"] in {"queued", "processing"}:
                            track.update(status="failed", error="El servidor se reinició. Vuelve a convertir este audio.")
                    job.update(status="failed", error="El servidor se reinició durante la conversión.",
                               message="La conversión se interrumpió. Puedes volver a intentarla.", updated_at=utc_now())
                    self._persist(job)
            except (OSError, ValueError, KeyError, TypeError):
                continue

    def cleanup(self):
        with self.lock:
            for job_id, job in list(self.jobs.items()):
                if job["status"] not in {"completed", "failed"}:
                    continue
                try:
                    age = time.time() - datetime.fromisoformat(job["updated_at"]).timestamp()
                except (ValueError, KeyError):
                    continue
                if age > JOB_TTL:
                    shutil.rmtree(self.root / job_id, ignore_errors=True)
                    self.jobs.pop(job_id, None)

    def _persist(self, job):
        destination = self.root / job["id"] / "job.json"
        temporary = destination.with_suffix(".tmp")
        temporary.write_text(json.dumps(job, ensure_ascii=False))
        temporary.replace(destination)

    def update(self, job, **fields):
        with self.lock:
            job.update(fields, updated_at=utc_now())
            self._persist(job)

    def new(self, options: dict, kind: str) -> dict:
        self.cleanup()
        with self.lock:
            pending = sum(job["status"] in {"queued", "processing"} for job in self.jobs.values())
            if pending >= MAX_PENDING_JOBS:
                raise HTTPException(429, "Hay varias conversiones en curso. Inténtalo de nuevo en unos minutos.")
            job_id = str(uuid4())
            (self.root / job_id).mkdir(mode=0o700)
            job = {"id": job_id, "status": "queued", "progress": 0, "message": "En la cola de conversión…",
                   "tracks": [], "options": options, "kind": kind, "created_at": utc_now(), "updated_at": utc_now()}
            self.jobs[job_id] = job
            self._persist(job)
            return job

    def get(self, job_id):
        self.cleanup()
        with self.lock:
            if not valid_id(job_id) or job_id not in self.jobs:
                raise HTTPException(404, "Esta conversión no existe o sus archivos ya caducaron.")
            # Return a snapshot; routes must not leak mutable state to encoders.
            return json.loads(json.dumps(self.jobs[job_id]))

    def public(self, job):
        snapshot = self.get(job["id"])
        snapshot.pop("options", None)
        for track in snapshot["tracks"]:
            for private in ("source", "info", "remote"):
                track.pop(private, None)
            if track["status"] == "completed":
                track["download_url"] = f'/api/jobs/{job["id"]}/download/{track["id"]}'
        if snapshot["status"] in {"completed", "failed"} and any(t["status"] == "completed" for t in snapshot["tracks"]):
            snapshot["zip_url"] = f'/api/jobs/{job["id"]}/zip'
        return snapshot

    def add_track(self, job, title, **fields):
        track_id = str(uuid4())
        directory = self.root / job["id"] / track_id
        directory.mkdir(mode=0o700)
        info = fields.pop("info", None)
        if info is not None:
            # Extraction objects can be lazy/non-JSON and contain temporary
            # signed media URLs. Keep those in memory, not in saved metadata.
            self.remote_sources[track_id] = info
            fields["remote"] = True
        track = {"id": track_id, "title": safe_title(title), "status": "queued", **fields}
        with self.lock:
            job["tracks"].append(track)
            self.update(job)
        return track, directory

    def discard(self, job):
        with self.lock:
            self.jobs.pop(job["id"], None)
            shutil.rmtree(self.root / job["id"], ignore_errors=True)

    def submit(self, job, urls=None):
        self.executor.submit(self._run, job, urls)

    def _run(self, job, urls):
        self.update(job, status="processing", message="Preparando los audios…", progress=1)
        try:
            if urls:
                for url in urls:
                    remaining = MAX_TRACKS - len(job["tracks"])
                    if remaining <= 0:
                        break
                    self.update(job, message="Buscando pistas públicas en SoundCloud…")
                    try:
                        for info in discover_soundcloud(url, remaining, MAX_UPLOAD_BYTES):
                            self.add_track(job, info.get("title") or "Pista de SoundCloud", info=info,
                                           artist=info.get("uploader") or info.get("artist"))
                    except ConversionError as exc:
                        track, _directory = self.add_track(job, "Enlace de SoundCloud")
                        track.update(status="failed", error=str(exc))
                        self.update(job)
            total = len(job["tracks"])
            for index, track in enumerate(job["tracks"]):
                if track["status"] == "failed":
                    continue
                directory = self.root / job["id"] / track["id"]
                track.update(status="processing")
                self.update(job, progress=int(index / max(1, total) * 95), message=f'Procesando {index + 1} de {total}: {track["title"]}')
                try:
                    if track.get("remote"):
                        def progress(value):
                            self.update(job, progress=min(95, int((index + value / 100) / max(1, total) * 95)))
                        source, info = download_soundcloud(self.remote_sources.pop(track["id"]), directory, MAX_UPLOAD_BYTES, progress)
                        track["title"] = safe_title(info.get("title") or track["title"])
                        track["artist"] = info.get("uploader") or info.get("artist")
                    else:
                        source = directory / track.pop("source")
                    extension = FORMATS[job["options"]["format"]]
                    filename = f'{safe_title(track["title"])}.{extension}'
                    destination = directory / filename
                    # Uploaded sources have fixed source.* names and cannot be
                    # overwritten by an audio named "source".
                    if destination == source:
                        destination = directory / f'{safe_title(track["title"])}-convertido.{extension}'
                        filename = destination.name
                    self.update(job, message=f'Convirtiendo {index + 1} de {total} a {job["options"]["format"].upper()}…',
                                progress=min(95, int((index + .5) / max(1, total) * 95)))
                    audio_info = convert_audio(source, destination, job["options"])
                    track.update(status="completed", filename=filename, size=destination.stat().st_size,
                                 duration=audio_info["duration"], source_format=audio_info["source_format"],
                                 sample_rate=job["options"]["sample_rate"], bit_depth=job["options"]["bit_depth"])
                except ConversionError as exc:
                    track.update(status="failed", error=str(exc))
                except Exception:
                    track.update(status="failed", error="No se pudo procesar este audio. Inténtalo con otro archivo.")
                finally:
                    track.pop("info", None)
                    track.pop("source", None)
                    track.pop("remote", None)
                    self.remote_sources.pop(track["id"], None)
                    # Keep only the final, ready output. Partial downloads and
                    # uploaded originals must not occupy storage after a job.
                    for file in directory.iterdir():
                        if file.is_file() and file.name != track.get("filename"):
                            file.unlink(missing_ok=True)
                    self.update(job, progress=int((index + 1) / max(1, total) * 100))
            done = sum(t["status"] == "completed" for t in job["tracks"])
            failed = len(job["tracks"]) - done
            if done:
                message = f'{done} audio(s) listo(s) para descargar.'
                if failed:
                    message += f' {failed} no se pudo/pudieron convertir.'
                self.update(job, status="completed", progress=100, message=message)
            else:
                failure = next((t.get("error") for t in job["tracks"] if t.get("error")), "No se encontraron audios para convertir.")
                self.update(job, status="failed", progress=100, message=failure, error=failure)
        except Exception:
            self.update(job, status="failed", progress=100, message="La conversión se interrumpió. Vuelve a intentarlo.",
                        error="No se pudo completar la conversión.")

    def track_file(self, job_id, track_id):
        job = self.get(job_id)
        if not valid_id(track_id):
            raise HTTPException(404, "El archivo no existe.")
        track = next((track for track in job["tracks"] if track["id"] == track_id), None)
        if not track or track["status"] != "completed":
            raise HTTPException(404, "El archivo todavía no está disponible.")
        path = self.root / job_id / track_id / track["filename"]
        if not path.is_file() or path.is_symlink() or not path.resolve().is_relative_to(self.root):
            raise HTTPException(404, "El archivo ya no está disponible.")
        return path


def create_app(data_dir: Path | None = None) -> FastAPI:
    manager = JobManager(data_dir or Path(os.getenv("ONDA_DATA_DIR", str(BASE_DIR / ".data"))))

    @asynccontextmanager
    async def lifespan(_app):
        async def scheduled_cleanup():
            while True:
                await asyncio.sleep(60)
                await asyncio.to_thread(manager.cleanup)
        cleanup_task = asyncio.create_task(scheduled_cleanup())
        try:
            yield
        finally:
            cleanup_task.cancel()
            try:
                await cleanup_task
            except asyncio.CancelledError:
                pass
            manager.executor.shutdown(wait=True)
            manager.cleanup()

    app = FastAPI(title="Onda", version="1.0.0", lifespan=lifespan)
    app.add_middleware(BodyLimitMiddleware)
    app.state.manager = manager

    @app.exception_handler(RequestValidationError)
    async def validation_error(_request, exc):
        messages = [error.get("msg", "") for error in exc.errors()]
        detail = next((message.removeprefix("Value error, ") for message in messages if "SoundCloud" in message),
                      "Revisa los enlaces, archivos y opciones de conversión.")
        return JSONResponse(status_code=422, content={"detail": detail})

    @app.middleware("http")
    async def response_headers(request, call_next):
        response = await call_next(request)
        response.headers["X-Content-Type-Options"] = "nosniff"
        response.headers["Referrer-Policy"] = "same-origin"
        if request.url.path.startswith("/api/"):
            response.headers["Cache-Control"] = "no-store"
        return response

    def require_converter():
        if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
            raise HTTPException(503, "Falta FFmpeg o FFprobe en el servidor para convertir audio.")

    @app.get("/api/health")
    def health():
        return {"status": "ok", "ffmpeg": bool(shutil.which("ffmpeg") and shutil.which("ffprobe")),
                "soundcloud": provider_available(), "soundcloud_connectivity": "not_checked",
                "max_upload_mb": MAX_UPLOAD_BYTES // 1024 // 1024, "max_tracks": MAX_TRACKS,
                "max_urls": 20, "max_batch_upload_mb": MAX_UPLOAD_BYTES * 2 // 1024 // 1024,
                "job_ttl_hours": JOB_TTL / 3600}

    @app.post("/api/jobs", status_code=202)
    def create_job(payload: URLJob):
        require_converter()
        if not provider_available():
            raise HTTPException(503, "Falta el componente de SoundCloud en el servidor. Puedes subir archivos de audio.")
        job = manager.new(payload.model_dump(exclude={"urls"}), "soundcloud")
        manager.submit(job, payload.urls)
        return manager.public(job)

    @app.post("/api/uploads", status_code=202)
    async def upload(files: list[UploadFile] = File(...), format: str = Form("wav"),
                     sample_rate: int = Form(44100), bit_depth: int = Form(16), normalize: bool = Form(False)):
        require_converter()
        try:
            options = ConversionOptions(format=format, sample_rate=sample_rate, bit_depth=bit_depth, normalize=normalize)
        except ValidationError as exc:
            raise HTTPException(422, "Revisa el formato, la frecuencia y la profundidad de bits.") from exc
        if not files or len(files) > MAX_TRACKS:
            raise HTTPException(422, f"Selecciona entre 1 y {MAX_TRACKS} archivos de audio.")
        job = manager.new(options.model_dump(), "upload")
        total_size = 0
        try:
            for uploaded in files:
                filename = (uploaded.filename or "audio").replace("\\", "/").rsplit("/", 1)[-1]
                extension = Path(filename).suffix.lower()
                if extension not in UPLOAD_EXTENSIONS:
                    raise HTTPException(422, "Selecciona archivos de audio WAV, MP3, FLAC, OGG, AAC, M4A, AIFF, WMA o WebM.")
                track, directory = manager.add_track(job, Path(filename).stem or "audio", source=f"source{extension}")
                written = 0
                with (directory / f"source{extension}").open("xb") as destination:
                    while chunk := await uploaded.read(1024 * 1024):
                        written += len(chunk)
                        total_size += len(chunk)
                        if written > MAX_UPLOAD_BYTES:
                            raise HTTPException(413, f"Cada archivo puede ocupar como máximo {MAX_UPLOAD_BYTES // 1024 // 1024} MB.")
                        if total_size > MAX_UPLOAD_BYTES * 2:
                            raise HTTPException(413, f"El lote completo puede ocupar como máximo {MAX_UPLOAD_BYTES * 2 // 1024 // 1024} MB.")
                        destination.write(chunk)
                if not written:
                    raise HTTPException(422, "Uno de los archivos está vacío.")
            manager.submit(job)
            return manager.public(job)
        except BaseException:
            manager.discard(job)
            raise
        finally:
            for uploaded in files:
                await uploaded.close()

    @app.get("/api/jobs/{job_id}")
    def get_job(job_id: str):
        return manager.public(manager.get(job_id))

    @app.get("/api/jobs/{job_id}/download/{track_id}")
    def download(job_id: str, track_id: str):
        path = manager.track_file(job_id, track_id)
        media_type = {".wav": "audio/wav", ".mp3": "audio/mpeg", ".flac": "audio/flac",
                      ".ogg": "audio/ogg", ".m4a": "audio/mp4"}.get(path.suffix, "application/octet-stream")
        return FileResponse(path, media_type=media_type, filename=path.name)

    @app.get("/api/jobs/{job_id}/zip")
    def download_zip(job_id: str):
        job = manager.get(job_id)
        if job["status"] not in {"completed", "failed"}:
            raise HTTPException(409, "Espera a que termine la conversión para descargar el ZIP.")
        completed = [track for track in job["tracks"] if track["status"] == "completed"]
        if not completed:
            raise HTTPException(404, "No hay archivos convertidos para descargar.")
        with manager.lock:
            path = manager.root / job_id / "onda-audios.zip"
            if not path.is_file():
                with zipfile.ZipFile(path, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=1) as archive:
                    for index, track in enumerate(completed, 1):
                        audio_path = manager.track_file(job_id, track["id"])
                        archive.write(audio_path, arcname=f'{index:02d}-{audio_path.name}')
        return FileResponse(path, media_type="application/zip", filename="onda-audios.zip")

    @app.get("/")
    def home():
        path = BASE_DIR / "static" / "index.html"
        if not path.is_file():
            raise HTTPException(503, "La interfaz todavía no está disponible.")
        return FileResponse(path)

    app.mount("/static", StaticFiles(directory=BASE_DIR / "static"), name="static")
    return app


app = create_app()
