"""Optional UI regression. Install Playwright for Python and Chrome, then run this file."""
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[2]

def assets(route):
    path = urlsplit(route.request.url).path.strip("/") or "index.html"
    if path == "mock.js":
        route.fulfill(content_type="text/javascript", body="""
          import { makeMock as original } from './original-mock.js';
          import { D } from './mmk3.js';
          export function makeMock() {
            const mock = original({delay: 120});
            window.savedChannel = () => mock.dev.saved[D.FIELDS.channel[0]] + 1;
            return mock;
          }
        """)
        return
    if path == "original-mock.js":
        path = "mock.js"
    base = root if path.startswith("flasher/") else root / "tools/ui"
    file = base / path
    if file.is_file():
        route.fulfill(path=file, content_type="text/javascript" if file.suffix == ".js" else "text/html")
    else:
        route.fulfill(status=404)

with sync_playwright() as driver:
    browser = driver.chromium.launch(channel="chrome")
    page = browser.new_page()
    page.route("**/*", assets)
    page.goto("http://localhost:18884/?mock")
    page.locator("#btn-connect").click()
    page.wait_for_function("document.querySelector('#status-text').textContent.startsWith('Connected to')")
    # Two ordinary editor changes around Send, in one turn, so the mock's ACK always arrives last.
    page.evaluate("""() => {
      const channel = document.querySelector('#f-channel');
      function edit(value) { channel.value = value; channel.dispatchEvent(new Event('change')); }
      edit('1'); document.querySelector('#btn-send').click(); edit('2');
    }""")
    page.wait_for_function("document.querySelector('#status-text').textContent.startsWith('Sent.')")
    assert page.locator('#chip-sync').text_content() == 'Edited, not sent'
    assert page.locator('#btn-send').is_enabled()
    page.locator('#btn-save').click()
    page.wait_for_function("document.querySelector('#status-text').textContent.startsWith('Saved on the device.')")
    assert page.evaluate('savedChannel()') == 3
    page.locator('#btn-read').click()
    page.wait_for_function("document.querySelector('#status-text').textContent.startsWith('Read the configuration')")
    assert page.locator('#f-channel').input_value() == '2'  # MIDI channel 3
    page.locator('#live').evaluate('el => el.click()')
    page.evaluate('''() => {
      const channel = document.querySelector('#f-channel');
      channel.value = '3'; channel.dispatchEvent(new Event('change'));
      document.querySelector('#btn-save').click();
      channel.value = '4'; channel.dispatchEvent(new Event('change'));
    }''')
    page.wait_for_function("document.querySelector('#chip-sync').textContent === 'On the device, not saved'")
    page.locator('#btn-read').click()
    page.wait_for_function("document.querySelector('#status-text').textContent.startsWith('Read the configuration')")
    assert page.locator('#f-channel').input_value() == '4'  # MIDI channel 5 active
    assert page.locator('#chip-sync').text_content() == 'On the device, not saved'
    assert page.evaluate('savedChannel()') == 4
    print('PASS: edits across manual Send, Save and live sending')
    browser.close()
