"""Optional UI regression. Install Playwright for Python and Chrome, then run this file."""
from pathlib import Path
from urllib.parse import urlsplit
from playwright.sync_api import sync_playwright

root = Path(__file__).resolve().parents[2]

def assets(route):
    path = urlsplit(route.request.url).path.strip("/") or "index.html"
    base = root if path.startswith("flasher/") else root / "tools/ui"
    file = base / path
    if file.is_file():
        route.fulfill(path=file, content_type="text/javascript" if file.suffix == ".js" else "text/html")
    else:
        route.fulfill(status=404)

with sync_playwright() as driver:
    browser = driver.chromium.launch(channel="chrome")
    # Only test the UI state machine. Dummy arrays have different lengths and cannot be flashed.
    preview = browser.new_page()
    def preview_assets(route):
        path = urlsplit(route.request.url).path
        if path == '/patch.js':
            js = """export async function findStockImage(input) {
                      if (input[0] === 9) await new Promise(r => { window.finishFile = r; });
                      return input;
                    }
                    export function buildImage() { return new Promise(resolve => {
                      window.finishPreview = () => resolve(new Uint8Array(7));
                    }); }"""
            route.fulfill(body=js, content_type='text/javascript')
        elif path == '/flasher/dfu.js':
            route.fulfill(body='''export const VID=1, PID_DFU=2, PID_RUNTIME=3;
                export const validateImage = () => [];
                export const readConfigDescriptor = async () => null;
                export const findDfuInterface = () => ({runtime:false, number:0});
                export const webUsbTransport = () => ({});
                export async function download(_, bytes) {
                  window.written = Array.from(bytes);
                  return {};
                }''', content_type='text/javascript')
        elif path == '/patch_bundle.json':
            route.fulfill(json={'stock_sha256': 'stock-test', 'result_sha256': 'patch-test'})
        else:
            assets(route)
    preview.route('**/*', preview_assets)
    preview.add_init_script("""Object.defineProperty(navigator, 'usb', { value: {
      requestDevice: async () => ({vendorId:1, productId:2, configuration:{},
                                  open:async()=>{}, claimInterface:async()=>{}, close:async()=>{}}),
      getDevices: async () => []
    } });""")
    preview.goto("http://localhost:18884/?mock")
    preview.locator('#file-fw').set_input_files({'name': 'ui-fixture', 'mimeType': 'application/octet-stream', 'buffer': b'abc'})
    preview.wait_for_function('typeof window.finishPreview === "function"')
    preview.evaluate("""() => document.querySelector('input[name=fwmode][value=stock]').click()""")
    assert '3 bytes' in preview.locator('#img-result').text_content()
    preview.evaluate('window.finishPreview()')
    preview.evaluate('() => new Promise(requestAnimationFrame)')
    assert '3 bytes' in preview.locator('#img-result').text_content(), 'stale build replaced restore bytes'
    assert 'stock-test' in preview.locator('#img-result').text_content()
    preview.locator('#ack').evaluate('el => el.click()')
    def choose(data):
        preview.locator('#file-fw').set_input_files({
            'name':'fixture', 'mimeType':'application/octet-stream', 'buffer':data})
    choose(bytes([9, 0]))
    preview.wait_for_function('typeof window.finishFile === "function"')
    choose(b'12345')
    preview.wait_for_function("document.querySelector('#img-result').textContent.includes('5 bytes')")
    preview.evaluate('window.finishFile()')
    preview.evaluate('() => new Promise(requestAnimationFrame)')
    assert '5 bytes' in preview.locator('#img-result').text_content()
    assert not preview.locator('#ack').is_checked()
    assert preview.locator('#btn-flash').is_disabled()
    preview.locator('#btn-usb').evaluate('el => el.click()')
    preview.wait_for_function("document.querySelector('#usb-result').textContent.includes('bootloader')")
    preview.locator('#ack').evaluate('el => el.click()')
    preview.locator('#btn-flash').evaluate('el => el.click()')
    preview.wait_for_function('Array.isArray(window.written)')
    assert preview.evaluate('window.written') == list(b'12345')
    print('PASS: late file and build results leave the selected image intact')
    browser.close()
