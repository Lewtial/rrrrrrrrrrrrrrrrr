"""Validate the static site with real offline browser conversion and downloads."""
from __future__ import annotations

import argparse
import io
import json
import math
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
from urllib.parse import urljoin
import wave
import zipfile

from playwright.sync_api import Error as PlaywrightError, sync_playwright


def inspect_wav(data: bytes, bits: int, rate: int, normalized: bool = False) -> dict:
    assert data[:4] == b"RIFF" and data[8:12] == b"WAVE"
    assert int.from_bytes(data[4:8], "little") == len(data) - 8
    with wave.open(io.BytesIO(data)) as audio:
        assert audio.getnchannels() == 2
        assert audio.getsampwidth() == bits // 8
        assert audio.getframerate() == rate
        duration = audio.getnframes() / rate
        assert 0.1 < duration < 5
        samples = audio.readframes(audio.getnframes())
    width = bits // 8
    peak = max(abs(int.from_bytes(samples[i:i + width], "little", signed=True))
               for i in range(0, len(samples), width)) / (2 ** (bits - 1))
    assert peak > 0.01, "Converted audio is silent"
    dbfs = 20 * math.log10(peak)
    if normalized:
        assert abs(dbfs + 1) < 0.002, dbfs
    return {"bits": bits, "sample_rate": rate, "channels": 2,
            "duration": round(duration, 4), "peak_dbfs": round(dbfs, 5), "bytes": len(data)}


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8002/onda-pages/")
    parser.add_argument("--standalone", type=Path, required=True)
    args = parser.parse_args()
    site = Path(__file__).resolve().parents[1]
    artifacts = site / "artifacts"
    artifacts.mkdir(exist_ok=True)
    report_path = artifacts / "browser-report.json"
    report_path.unlink(missing_ok=True)
    errors: list[str] = []
    network: list[dict] = []
    checks: list[str] = []

    with tempfile.TemporaryDirectory(prefix="onda-pages-") as temporary:
        fixtures = []
        for index, frequency in enumerate([440, 660], 1):
            path = Path(temporary) / f"canción-{index}.mp3"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                f"sine=frequency={frequency}:sample_rate=22050:duration=1.2",
                "-ac", "1", "-c:a", "libmp3lame", str(path),
            ], check=True, timeout=20)
            fixtures.append(path)

        with sync_playwright() as p:
            options = {"headless": True, "args": ["--no-sandbox"]}
            executable = os.environ.get("CHROMIUM_EXECUTABLE") or shutil.which("chromium")
            if executable:
                options["executable_path"] = executable
            browser = p.chromium.launch(**options)
            context = browser.new_context(viewport={"width": 1440, "height": 1000},
                                          accept_downloads=True, timezone_id="America/Bogota")
            context.on("request", lambda request: network.append({"url": request.url, "method": request.method}))
            page = context.new_page()
            page.on("pageerror", lambda error: errors.append(str(error)))
            page.goto(args.base_url, wait_until="networkidle")
            assert page.locator("html").get_attribute("lang") == "es"
            assert page.evaluate("window.OndaAudio.supported")
            assert page.locator("#source-urls").count() == 0
            page.screenshot(path=str(artifacts / "desktop.png"), full_page=True)
            checks.append("Spanish static homepage works below a project subpath")

            await_network_count = len(network)
            context.set_offline(True)
            page.locator("#source-files").set_input_files([str(path) for path in fixtures])
            page.locator("details.advanced > summary").click()
            page.locator("#sample-rate").select_option("48000")
            page.locator("#bit-depth").select_option("24")
            page.locator("#normalize").check()
            page.locator("#convert-button").click()
            page.locator("#download-zip").wait_for(state="visible", timeout=60000)
            assert page.locator("#job-progress").get_attribute("aria-valuenow") == "100"
            files = page.locator("#track-list a[download]")
            assert files.count() == 2, page.locator("#track-list").inner_text()
            with page.expect_download() as pending:
                files.first.click()
            output = artifacts / "offline-converted.wav"
            pending.value.save_as(output)
            wav24 = inspect_wav(output.read_bytes(), 24, 48000, True)
            checks.append("Offline two-file MP3 to stereo WAV24/48 kHz with measured -1 dBFS peaks")

            with page.expect_download() as pending:
                page.locator("#download-zip").click()
            archive = artifacts / "offline-converted.zip"
            pending.value.save_as(archive)
            with zipfile.ZipFile(archive) as package:
                assert package.testzip() is None
                assert len(package.namelist()) == 2
                for name in package.namelist():
                    inspect_wav(package.read(name), 24, 48000, True)
                assert any("canción" in name for name in package.namelist())
            assert not [request for request in network[await_network_count:]
                        if request["url"].startswith(("http:", "https:"))], network[await_network_count:]
            page.screenshot(path=str(artifacts / "converted.png"), full_page=True)
            checks.append("Offline UTF-8 ZIP contains both real WAVs; conversion makes no HTTP requests")

            context.set_offline(False)
            page.reload(wait_until="networkidle")
            context.set_offline(True)
            page.locator("#history-toggle").click()
            page.locator("#history-list button.history-item").first.wait_for(state="visible")
            page.locator("#history-list button.history-item").first.click()
            recovered = page.locator("#track-list a[download]")
            recovered.first.wait_for(state="visible")
            assert recovered.count() == 2
            with page.expect_download() as pending:
                recovered.first.click()
            restored = artifacts / "restored.wav"
            pending.value.save_as(restored)
            inspect_wav(restored.read_bytes(), 24, 48000, True)
            checks.append("IndexedDB restores actual downloadable WAV files after reload")
            page.locator("#clear-history").click()
            page.wait_for_function("document.querySelectorAll('#history-list button.history-item').length === 0")

            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("scrollTo(0,0)")
            assert page.evaluate("document.documentElement.scrollWidth <= innerWidth")
            page.screenshot(path=str(artifacts / "mobile.png"), full_page=True)
            checks.append("History clears and mobile layout has no horizontal overflow")
            context.close()

            # Test file:// when policy permits it. Do not change managed-browser
            # policies; an explicitly blocked scheme is reported separately.
            local = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True)
            local.set_offline(True)
            local_requests: list[str] = []
            local.on("request", lambda request: local_requests.append(request.url))
            demo = local.new_page()
            demo.on("pageerror", lambda error: errors.append(str(error)))
            standalone_target = args.standalone.resolve().as_uri()
            file_open = "verified"
            try:
                demo.goto(standalone_target, wait_until="load")
            except PlaywrightError as error:
                if "ERR_BLOCKED_BY_ADMINISTRATOR" not in str(error):
                    raise
                file_open = "blocked_by_managed_browser_policy"
                standalone_target = urljoin(args.base_url, "../web/" + args.standalone.name)
                local.set_offline(False)
                demo.goto(standalone_target, wait_until="networkidle")
                local.set_offline(True)
            assert demo.evaluate("window.OndaAudio.supported")
            demo.locator("#demo-button").click()
            demo.locator("#convert-button").click()
            demo.locator("#download-zip").wait_for(state="visible", timeout=30000)
            with demo.expect_download() as pending:
                demo.locator("#track-list a[download]").first.click()
            result = artifacts / "standalone-demo.wav"
            pending.value.save_as(result)
            wav16 = inspect_wav(result.read_bytes(), 16, 44100)
            assert all(url == standalone_target for url in local_requests if url.startswith(("http:", "https:")))
            checks.append("Single HTML generates/downloads a real WAV16 demo offline without extra assets or services")

            # Reject broken audio while still converting a valid file in the same batch.
            broken = local.new_page()
            broken.on("pageerror", lambda error: errors.append(str(error)))
            if file_open != "verified":
                local.set_offline(False)
            broken.goto(standalone_target, wait_until="load")
            local.set_offline(True)
            broken.locator("#source-files").set_input_files([
                {"name": "broken.wav", "mimeType": "audio/wav", "buffer": b"not a real audio file"},
                {"name": "valid.mp3", "mimeType": "audio/mpeg", "buffer": fixtures[0].read_bytes()},
            ])
            broken.locator("#convert-button").click()
            broken.locator("#download-zip").wait_for(state="visible", timeout=30000)
            assert broken.locator("#track-list a[download]").count() == 1
            assert "broken" in broken.locator("#track-list").inner_text().lower()
            checks.append("Broken audio reports a track failure while a valid track remains downloadable")
            assert not errors, errors
            assert not [request for request in network if request["method"] != "GET"]
            assert not [request for request in network if "/api/" in request["url"]]
            browser.close()

    report = {"status": "passed", "checks": checks, "browser_errors": errors,
              "file_open": file_open,
              "wav24": wav24, "wav16": wav16,
              "http_requests": [request for request in network if request["url"].startswith(("http:", "https:"))]}
    report_path.write_text(json.dumps(report, ensure_ascii=False, indent=2) + "\n")
    print(json.dumps(report, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
