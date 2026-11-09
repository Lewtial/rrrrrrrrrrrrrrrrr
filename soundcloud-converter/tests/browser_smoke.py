"""Exercise the real upload/conversion/download flow in Chromium.

Start the app first, then run this script. No remote audio or mocked responses
are used. Browser assets and reports are written to the ignored artifacts dir.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import tempfile
import zipfile

from playwright.sync_api import sync_playwright


def probe(path: Path) -> dict:
    return json.loads(subprocess.check_output([
        "ffprobe", "-v", "error", "-select_streams", "a:0",
        "-show_entries", "stream=codec_name,sample_rate,channels,bits_per_sample",
        "-of", "json", str(path),
    ], text=True))["streams"][0]


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--base-url", default="http://127.0.0.1:8000")
    args = parser.parse_args()
    artifacts = Path(__file__).resolve().parents[1] / "artifacts"
    artifacts.mkdir(exist_ok=True)
    (artifacts / "browser-report.json").unlink(missing_ok=True)
    failures: list[str] = []
    checks: list[str] = []

    with tempfile.TemporaryDirectory(prefix="onda-browser-") as temporary:
        fixtures = []
        for number, frequency in enumerate([440, 660], start=1):
            path = Path(temporary) / f"prueba-{number}.mp3"
            subprocess.run([
                "ffmpeg", "-v", "error", "-f", "lavfi", "-i",
                f"sine=frequency={frequency}:sample_rate=22050:duration=1.2",
                "-ac", "1", "-c:a", "libmp3lame", str(path),
            ], check=True, timeout=20)
            fixtures.append(path)

        with sync_playwright() as playwright:
            executable = os.environ.get("CHROMIUM_EXECUTABLE") or shutil.which("chromium")
            launch = {"headless": True, "args": ["--no-sandbox"]}
            if executable:
                launch["executable_path"] = executable
            browser = playwright.chromium.launch(**launch)
            context = browser.new_context(viewport={"width": 1440, "height": 1000}, accept_downloads=True,
                                          timezone_id="America/Bogota")
            page = context.new_page()
            page.on("pageerror", lambda error: failures.append(str(error)))
            page.goto(args.base_url, wait_until="networkidle")
            assert page.locator("html").get_attribute("lang") == "es"
            assert "Onda" in page.title()
            page.screenshot(path=str(artifacts / "desktop.png"), full_page=True)
            checks.append("Spanish homepage and desktop rendering")

            page.locator('input[name="format"][value="mp3"]').check()
            assert "MP3" in page.locator("#convert-label").inner_text()
            page.locator('input[name="format"][value="wav"]').check()
            page.locator("#tab-file").click()
            page.locator("#source-files").set_input_files([str(path) for path in fixtures])
            assert page.locator("#selected-files").is_visible()
            page.locator("details.advanced > summary").click()
            page.locator("#sample-rate").select_option("48000")
            page.locator("#bit-depth").select_option("24")
            page.locator("#normalize").check()
            page.locator("#convert-button").click()
            page.locator("#download-zip").wait_for(state="visible", timeout=60000)
            assert page.locator("#job-progress").get_attribute("aria-valuenow") == "100"
            downloads = page.locator('#track-list a[href*="/download/"]')
            assert downloads.count() == 2, page.locator("#track-list").inner_text()

            with page.expect_download() as pending:
                downloads.first.click()
            wav = artifacts / "converted.wav"
            pending.value.save_as(wav)
            audio = probe(wav)
            assert audio["codec_name"] == "pcm_s24le", audio
            assert audio["sample_rate"] == "48000" and audio["channels"] == 2, audio
            checks.append("Two real MP3 uploads converted to normalized stereo WAV, 24 bit / 48 kHz")

            with page.expect_download() as pending:
                page.locator("#download-zip").click()
            archive = artifacts / "converted.zip"
            pending.value.save_as(archive)
            with zipfile.ZipFile(archive) as package:
                assert package.testzip() is None
                assert len(package.namelist()) == 2
                assert all(name.endswith(".wav") for name in package.namelist())
            page.screenshot(path=str(artifacts / "conversion-completed.png"), full_page=True)
            checks.append("Individual WAV download and valid two-track ZIP")

            page.locator("#history-toggle").click()
            assert page.locator("#history-panel").is_visible()
            assert page.locator("#history-list").inner_text().strip()
            page.reload(wait_until="networkidle")
            page.locator("#history-toggle").click()
            assert page.locator("#history-list").inner_text().strip()
            checks.append("Conversion history survives page reload")

            page.locator("#tab-url").click()
            page.locator("#source-urls").fill("https://example.com/not-soundcloud")
            page.locator("#convert-button").click()
            page.locator("#form-error").wait_for(state="visible")
            assert page.locator("#form-error").inner_text().strip()
            checks.append("Unsupported URL is rejected with a visible error")

            page.locator("#faq .faq-list details").first.locator("summary").click()
            assert page.locator("#faq .faq-list details").first.get_attribute("open") is not None
            checks.append("FAQ interaction")

            page.set_viewport_size({"width": 390, "height": 844})
            page.evaluate("window.scrollTo(0, 0)")
            page.wait_for_timeout(150)
            assert page.evaluate("document.documentElement.scrollWidth <= window.innerWidth"), "Mobile overflow"
            page.screenshot(path=str(artifacts / "mobile.png"), full_page=True)
            checks.append("390 px mobile rendering without horizontal overflow")
            assert not failures, failures
            browser.close()

    report = {"status": "passed", "checks": checks, "browser_errors": failures, "wav": audio}
    (artifacts / "browser-report.json").write_text(json.dumps(report, indent=2, ensure_ascii=False) + "\n")
    print(json.dumps(report, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
