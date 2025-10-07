# iOS Photos fresh-asset guard + Vision OCR helpers (Pythonista)

import time
import photos
from objc_util import ObjCClass, ObjCInstance

# Vision OCR setup
VNImageRequestHandler = ObjCClass('VNImageRequestHandler')
VNRecognizeTextRequest = ObjCClass('VNRecognizeTextRequest')

def _created_str(dt_obj):
    try:
        return dt_obj.strftime('%Y-%m-%d %H:%M:%S')
    except Exception:
        return ''

def _latest_asset():
    assets = photos.get_assets(media_type='image')[-1:]
    return assets[0] if assets else None

def _is_same(prev_asset_id: str | None, prev_created: str | None, asset) -> bool:
    if not asset:
        return False
    aid = getattr(asset, 'local_id', None)
    created = getattr(asset, 'creation_date', None)
    created_s = _created_str(created) if created else ''
    same_id = (aid and prev_asset_id and aid == prev_asset_id)
    same_time = (created_s and prev_created and created_s == prev_created)
    return bool(same_id or same_time)

def wait_fresh_asset(prev_asset_id: str | None, prev_created: str | None, poll: float = 0.08):
    """
    Blocks until Photos returns a *new* image whose local_id or creation_date
    differs from what we last processed. No timeout by design.
    """
    # tiny grace so iOS finishes writing the new screenshot
    time.sleep(0.15)
    attempt = 0
    while True:
        attempt += 1
        asset = _latest_asset()
        if asset is None:
            time.sleep(poll)
            continue

        created = getattr(asset, 'creation_date', None)
        created_s = _created_str(created) if created else ''
        aid = getattr(asset, 'local_id', None)

        if not _is_same(prev_asset_id, prev_created, asset):
            print(f"[guard] Fresh asset detected on attempt {attempt} | id={aid} | created={created_s}", flush=True)
            return asset

        time.sleep(poll)

def cgimage_from_asset(asset):
    """
    Convert a Photos asset to CGImage for Vision OCR.
    """
    uiimage = asset.get_ui_image()
    objc_image = ObjCInstance(uiimage)
    return objc_image.CGImage()

def run_ocr(cgimage):
    """
    Run Vision OCR on a CGImage and return (text, elapsed_seconds).
    Text lines are prefixed with '• ' to mirror your original output.
    """
    start_time = time.perf_counter()
    handler = VNImageRequestHandler.alloc().initWithCGImage_options_(cgimage, None)
    request = VNRecognizeTextRequest.alloc().init()
    handler.performRequests_error_([request], None)
    ocr_time = time.perf_counter() - start_time

    ocr_text = ''
    for r in request.results():
        ocr_text += f'• {r.text()}\n'
    return ocr_text, ocr_time
