from __future__ import annotations

import io
import asyncio
import json
import math
from pathlib import Path
import struct
import subprocess
import sys
import time
from urllib.request import Request
import wave
import zipfile

import pytest
import httpx
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import app as backend
import converter


def sine_wave(seconds=.2):
    target = io.BytesIO()
    with wave.open(target, "wb") as audio:
        audio.setnchannels(1)
        audio.setsampwidth(2)
        audio.setframerate(22050)
        audio.writeframes(b"".join(struct.pack("<h", int(10000 * math.sin(2 * math.pi * 440 * i / 22050)))
                                   for i in range(int(seconds * 22050))))
    return target.getvalue()


@pytest.fixture
def client(tmp_path):
    application = backend.create_app(tmp_path / "audio-data")
    with TestClient(application) as value:
        yield value


def completed_job(client, response):
    assert response.status_code == 202, response.text
    job = response.json()
    deadline = time.monotonic() + 30
    while job["status"] not in {"completed", "failed"}:
        assert time.monotonic() < deadline, job
        time.sleep(.03)
        response = client.get(f'/api/jobs/{job["id"]}')
        assert response.status_code == 200
        job = response.json()
    return job


@pytest.mark.parametrize("bits", [16, 24])
def test_real_wav_conversion_and_zip(client, bits):
    job = completed_job(client, client.post("/api/uploads", files=[("files", ("tono.wav", sine_wave(), "audio/wav"))],
                                          data={"format": "wav", "sample_rate": "48000", "bit_depth": str(bits), "normalize": "true"}))
    assert job["status"] == "completed", job
    assert job["progress"] == 100
    track = job["tracks"][0]
    assert track["status"] == "completed"
    assert not {"source", "info", "remote"}.intersection(track)
    result = client.get(track["download_url"])
    assert result.status_code == 200
    with wave.open(io.BytesIO(result.content)) as audio:
        assert audio.getframerate() == 48000
        assert audio.getnchannels() == 2
        assert audio.getsampwidth() == bits // 8
        assert .19 < audio.getnframes() / audio.getframerate() < .22
    archive_response = client.get(job["zip_url"])
    assert archive_response.status_code == 200
    with zipfile.ZipFile(io.BytesIO(archive_response.content)) as archive:
        assert archive.testzip() is None
        assert len(archive.namelist()) == 1
        assert archive.read(archive.namelist()[0]) == result.content
    directory = client.app.state.manager.root / job["id"] / track["id"]
    assert {path.name for path in directory.iterdir()} == {track["filename"]}


@pytest.mark.parametrize("format,codec,extension", [("mp3", "mp3", ".mp3"), ("flac", "flac", ".flac"),
                                                   ("ogg", "vorbis", ".ogg"), ("aac", "aac", ".m4a")])
def test_each_output_uses_a_real_audio_encoder(client, tmp_path, format, codec, extension):
    job = completed_job(client, client.post("/api/uploads", files={"files": ("sample.wav", sine_wave(), "audio/wav")},
                                          data={"format": format, "sample_rate": "44100", "bit_depth": "24"}))
    assert job["status"] == "completed", job
    track = job["tracks"][0]
    assert track["filename"].endswith(extension)
    result = client.get(track["download_url"])
    path = tmp_path / ("download" + extension)
    path.write_bytes(result.content)
    info = json.loads(subprocess.check_output(["ffprobe", "-v", "error", "-show_streams", "-of", "json", str(path)]))
    assert info["streams"][0]["codec_name"] == codec
    assert int(info["streams"][0]["sample_rate"]) == 44100
    assert info["streams"][0]["channels"] == 2


def test_batch_preserves_success_and_reports_invalid_audio(client):
    job = completed_job(client, client.post("/api/uploads", files=[
        ("files", ("first.wav", sine_wave(), "audio/wav")),
        ("files", ("broken.wav", b"This is not audio", "audio/wav")),
        ("files", ("second.wav", sine_wave(), "audio/wav")),
    ]))
    assert job["status"] == "completed"
    assert [track["status"] for track in job["tracks"]] == ["completed", "failed", "completed"]
    assert "error" in job["tracks"][1]
    with zipfile.ZipFile(io.BytesIO(client.get(job["zip_url"]).content)) as archive:
        assert len(archive.namelist()) == 2


@pytest.mark.parametrize("url", ["https://example.com/audio.wav", "http://soundcloud.com/a/b", "https://localhost/audio",
                                "https://soundcloud.com.evil.test/a", "https://soundcloud.com:443/a/b",
                                "https://user:secret@soundcloud.com/a/b", "https://@soundcloud.com/a/b",
                                "https://soundcloud.com/a/\nb", "file:///etc/passwd"])
def test_rejects_non_soundcloud_or_ambiguous_sources(client, url):
    response = client.post("/api/jobs", json={"urls": [url]})
    assert response.status_code == 422
    assert "secret" not in response.text


def test_rejects_upload_and_invalid_conversion_options_without_leftovers(client):
    manager = client.app.state.manager
    for files, data, expected in [
        ({"files": ("playlist.m3u", b"file:///etc/passwd")}, {}, 422),
        ({"files": ("empty.wav", b"")}, {}, 422),
        ({"files": ("audio.wav", sine_wave())}, {"format": "invalid"}, 422),
    ]:
        response = client.post("/api/uploads", files=files, data=data)
        assert response.status_code == expected
    assert list(manager.root.iterdir()) == []


def test_upload_size_limit_cleans_partial_files(client, monkeypatch):
    monkeypatch.setattr(backend, "MAX_UPLOAD_BYTES", 10)
    response = client.post("/api/uploads", files={"files": ("large.wav", sine_wave())})
    assert response.status_code == 413
    assert list(client.app.state.manager.root.iterdir()) == []


def test_oversized_content_length_rejected_before_multipart_parsing(client):
    response = client.post("/api/uploads", content=b"small", headers={"Content-Length": "999999999999"})
    assert response.status_code == 413
    assert list(client.app.state.manager.root.iterdir()) == []


def test_streamed_body_limit_closes_multipart_temporary_files(client, monkeypatch):
    import starlette.formparsers
    real_temporary_file = starlette.formparsers.SpooledTemporaryFile
    temporary_files = []

    def tracked_temporary_file(*args, **kwargs):
        result = real_temporary_file(*args, **kwargs)
        temporary_files.append(result)
        return result

    monkeypatch.setattr(starlette.formparsers, "SpooledTemporaryFile", tracked_temporary_file)
    monkeypatch.setattr(backend, "MAX_UPLOAD_BYTES", 10)

    async def run():
        async def body():
            yield b'--boundary\r\nContent-Disposition: form-data; name="files"; filename="large.wav"\r\nContent-Type: audio/wav\r\n\r\n' + b'a' * 100
            yield b'b' * (3 * 1024 * 1024)
            yield b'\r\n--boundary--\r\n'
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=client.app), base_url="http://test") as http:
            return await http.post("/api/uploads", content=body(), headers={"Content-Type": "multipart/form-data; boundary=boundary"})

    response = asyncio.run(run())
    assert response.status_code == 413, response.text
    assert temporary_files and all(file.closed for file in temporary_files)
    assert list(client.app.state.manager.root.iterdir()) == []


def test_unavailable_paths_do_not_read_other_files(client):
    assert client.get("/api/jobs/not-a-job").status_code == 404
    assert client.get("/api/jobs/00000000-0000-0000-0000-000000000000/download/not-a-track").status_code == 404
    response = client.get("/api/jobs/%2e%2e%2f%2e%2e/download/%2e%2e%2fetc%2fpasswd")
    assert response.status_code == 404


def test_network_failure_is_clear_and_does_not_leak_provider_internals(client, monkeypatch):
    def unavailable(*_args):
        raise converter.ConversionError("No se pudo acceder a SoundCloud. Puedes subir un archivo de audio.")
    monkeypatch.setattr(backend, "discover_soundcloud", unavailable)
    job = completed_job(client, client.post("/api/jobs", json={"urls": ["https://soundcloud.com/artist/track"]}))
    assert job["status"] == "failed"
    assert "SoundCloud" in job["error"]
    assert not job.get("zip_url")
    assert job["tracks"][0]["status"] == "failed"


def test_remote_pipeline_keeps_private_lazy_metadata_out_of_saved_jobs(client, monkeypatch):
    info = {"title": "Remote song", "uploader": "Artist", "lazy_metadata": object(),
            "url": "https://cf-media.sndcdn.com/temporary?token=not-for-history"}
    monkeypatch.setattr(backend, "discover_soundcloud", lambda *_args: [info])

    def local_provider(_info, directory, _limit, progress):
        progress(30)
        path = directory / "source.wav"
        path.write_bytes(sine_wave())
        return path, info

    monkeypatch.setattr(backend, "download_soundcloud", local_provider)
    job = completed_job(client, client.post("/api/jobs", json={"urls": ["https://soundcloud.com/artist/track"]}))
    assert job["status"] == "completed", job
    assert job["tracks"][0]["title"] == "Remote song"
    assert client.get(job["tracks"][0]["download_url"]).status_code == 200
    stored = (client.app.state.manager.root / job["id"] / "job.json").read_text()
    assert "not-for-history" not in stored
    assert "lazy_metadata" not in stored


def test_disguised_playlist_upload_cannot_read_external_files(client):
    payload = b"ffconcat version 1.0\nfile '/etc/passwd'\n"
    job = completed_job(client, client.post("/api/uploads", files={"files": ("pretend.wav", payload, "audio/wav")}))
    assert job["status"] == "failed"
    assert "audio válido" in job["tracks"][0]["error"]
    assert not job.get("zip_url")


def test_provider_redirects_and_protocols_are_guarded():
    guard = converter._SafeRedirect()
    for target in ["http://soundcloud.com/a/b", "https://127.0.0.1/secret", "https://evil.test/media", "file:///etc/passwd"]:
        with pytest.raises(converter.ConversionError):
            guard.redirect_request(Request("https://soundcloud.com/a/b"), None, 302, "", {}, target)
    for target in ["https://@soundcloud.com/a", "https://soundcloud.com/\nmedia", "https://sndcdn.com\\@127.0.0.1/a"]:
        with pytest.raises(converter.ConversionError):
            converter.validate_provider_url(target)


def test_hls_preflight_never_delegates_protected_streams_to_ffmpeg():
    if not converter.provider_available():
        pytest.skip("yt-dlp not installed")
    with converter.SoundCloudDownloader(converter._options(1, 1024 * 1024)) as downloader:
        with pytest.raises(converter.ConversionError):
            downloader.dl("unused.mp3", {
                "url": "https://cf-media.sndcdn.com/example.m3u8", "protocol": "m3u8_native", "ext": "mp3",
                "hls_media_playlist_data": '#EXTM3U\n#EXT-X-KEY:METHOD=AES-128,URI="https://cf-media.sndcdn.com/key"\n#EXTINF:2,\nhttps://cf-media.sndcdn.com/segment.ts\n',
            })


def test_progressive_http_label_still_requires_https_url(monkeypatch):
    if not converter.provider_available():
        pytest.skip("yt-dlp not installed")
    called = []
    monkeypatch.setattr(converter.HttpFD, "download", lambda self, *args: called.append(args) or (True, True))
    with converter.SoundCloudDownloader(converter._options(1, 1000)) as downloader:
        downloader.dl("unused.mp3", {"url": "https://cf-media.sndcdn.com/a.mp3", "protocol": "http"})
        assert called
        with pytest.raises(converter.ConversionError):
            downloader.dl("unused.mp3", {"url": "http://cf-media.sndcdn.com/a.mp3", "protocol": "http"})


def test_preview_is_rejected_instead_of_being_reported_as_complete(tmp_path):
    with pytest.raises(converter.ConversionError, match="vista previa"):
        converter.download_soundcloud({"url": "https://cf-media.sndcdn.com/preview/track.mp3", "protocol": "http",
                                      "format_id": "http_mp3_preview", "title": "Restricted track"},
                                     tmp_path, 1000000, lambda _value: None)


def test_metadata_survives_restart_and_active_jobs_are_not_expired(client):
    manager = client.app.state.manager
    job = manager.new(backend.ConversionOptions().model_dump(), "upload")
    manager.update(job, updated_at="2000-01-01T00:00:00+00:00")
    # update() overwrites timestamps intentionally; set old value under its lock.
    with manager.lock:
        job["updated_at"] = "2000-01-01T00:00:00+00:00"
        manager._persist(job)
    manager.cleanup()
    assert (manager.root / job["id"]).is_dir()
    restored = backend.JobManager(manager.root)
    try:
        snapshot = restored.get(job["id"])
        assert snapshot["status"] == "failed"
        assert "reinició" in snapshot["error"]
    finally:
        restored.executor.shutdown(wait=True)


def test_health_separates_installation_from_connectivity(client):
    response = client.get("/api/health")
    assert response.status_code == 200
    data = response.json()
    assert data["ffmpeg"] is True
    assert data["soundcloud_connectivity"] == "not_checked"
