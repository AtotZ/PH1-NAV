# File: TestSubjext/UberTripLogger.py
print("✅ Hello from GitHub! The sync is working.")
import photos
import datetime
import re
import os
import json
from objc_util import ObjCClass, ObjCInstance

script_dir = os.path.dirname(os.path.abspath(__file__))
config_path = os.path.join(script_dir, 'config.json')
with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)

VNImageRequestHandler = ObjCClass('VNImageRequestHandler')
VNRecognizeTextRequest = ObjCClass('VNRecognizeTextRequest')

assets = photos.get_assets(media_type='image')
latest_asset = assets[-1]
uiimage = latest_asset.get_ui_image()
objc_image = ObjCInstance(uiimage)
cgimage = objc_image.CGImage()

handler = VNImageRequestHandler.alloc().initWithCGImage_options_(cgimage, None)
request = VNRecognizeTextRequest.alloc().init()
handler.performRequests_error_([request], None)

ocr_text = ''
for r in request.results():
    ocr_text += f'• {r.text()}\n'

print(f'OCR result:\n{ocr_text}')

price_matches = re.findall(r'£\s*(\d+\.\d+)', ocr_text)
fares = [float(p) for p in price_matches if float(p) > 2.00]
main_price = max(fares) if fares else 0.0

star_rating = 0.0
for line in ocr_text.splitlines():
    if '£' in line:
        continue
    match = re.search(r'(\d\.\d{2})', line)
    if match:
        star_rating = float(match.group(1))
        break

star_status = "GOOD" if star_rating >= config['min_star'] else "RISKY"

def parse_hr_min(text):
    hr = re.search(r'(\d+)\s*hr', text)
    mi = re.search(r'(\d+)\s*min', text)
    h = int(hr.group(1)) if hr else 0
    m = int(mi.group(1)) if mi else 0
    return h * 60 + m

pairs = re.findall(r'((?:\d+\s*hr\s*)?\d+\s*min)[^\n]*\((\d+(\.\d+)?) mi\)', ocr_text)
pickup_min, pickup_miles = (parse_hr_min(pairs[0][0]), float(pairs[0][1])) if len(pairs) >= 1 else (0, 0.0)
trip_min, trip_miles = (parse_hr_min(pairs[1][0]), float(pairs[1][1])) if len(pairs) >= 2 else (0, 0.0)

if pickup_miles <= 1.0:
    pickup_status = "CLOSE"
elif pickup_miles <= 3.0 and pickup_min <= 10:
    pickup_status = "OK"
else:
    pickup_status = "TOO FAR"

per_mile = main_price / trip_miles if trip_miles else 0.0
per_min = main_price / trip_min if trip_min else 0.0
effective_hourly = per_min * 60 if per_min else 0.0

def violates_hard_rule(config, main_price, pickup_miles, pickup_min, trip_min, per_mile, per_min):
    for rule in config.get("hard_rules", []):
        try:
            if eval(rule["condition"], {}, {
                "price": main_price,
                "pickup_miles": pickup_miles,
                "pickup_min": pickup_min,
                "trip_min": trip_min,
                "per_mile": per_mile,
                "per_min": per_min
            }):
                return rule.get("short_reason", "Trip rejected"), rule.get("reason", "")
        except Exception:
            continue
    return None, None

def compute_score(per_mile, per_min, effective_hourly, pickup_status, star_rating, pickup_miles, trip_miles, config):
    score = 0
    w = config["scoring_weights"]

    score += w["per_mile"]["score"]["high"] if per_mile >= w["per_mile"]["high"] else \
             w["per_mile"]["score"]["mid"] if per_mile >= w["per_mile"]["mid"] else \
             w["per_mile"]["score"]["low"]

    score += w["per_min"]["score"]["high"] if per_min >= w["per_min"]["high"] else \
             w["per_min"]["score"]["mid"] if per_min >= w["per_min"]["mid"] else \
             w["per_min"]["score"]["low"]

    if effective_hourly >= w["effective_hourly"]["threshold"]:
        score += w["effective_hourly"]["score"]

    score += w["pickup_status"].get(pickup_status, 0)

    score += w["star_rating"]["score_if_good"] if star_rating >= config["min_star"] else \
             w["star_rating"]["score_if_risky"]

    if config.get("pickup_penalty", {}).get("enabled"):
        for rule in config["pickup_penalty"]["penalty_rules"]:
            try:
                if eval(rule["condition"], {}, {
                    "pickup_miles": pickup_miles,
                    "trip_miles": trip_miles
                }):
                    score -= rule["penalty"]
            except Exception:
                continue

    return score

short_reason, full_reason = violates_hard_rule(config, main_price, pickup_miles, pickup_min, trip_min, per_mile, per_min)
if short_reason:
    score = 0
    status = f"BAD ❌ {short_reason}"
else:
    score = compute_score(per_mile, per_min, effective_hourly, pickup_status, star_rating, pickup_miles, trip_miles, config)
    thresholds = config["score_status_thresholds"]
    if score >= thresholds["good"]:
        status = "GOOD ✅"
    elif score >= thresholds["ok"]:
        status = "OK 🤏"
    else:
        status = "BAD ❌"

now = datetime.datetime.now().strftime('%Y-%m-%d %H:%M:%S')
block = f"""
==============================
{now}

{ocr_text.strip()}

Pickup: {pickup_miles:.2f} mi | {pickup_min} min → {pickup_status}
Trip: {trip_miles:.2f} mi | {trip_min} min
Star Rating: {star_rating:.2f} → {star_status}
Price (highest): £{main_price:.2f}
£ per mile: £{main_price:.2f} ÷ {trip_miles:.2f} = £{per_mile:.2f}
£ per min: £{main_price:.2f} ÷ {trip_min} = £{per_min:.2f}
Effective £/hour: £{per_min:.2f} × 60 = £{effective_hourly:.2f}

STATUS: {status} | Score: {score}
{f"❗ Reason: {full_reason}" if full_reason else ""}

🔍 Logic used:
• ≥£2/mi = +2 | ≥£1.5 = +1 | <£1 = -1
• ≥£0.60/min = +2 | ≥£0.45 = +1 | <£0.30 = -1
• £/hr ≥ 40 = +1
• Pickup CLOSE = +1 | TOO FAR = -2
• Star GOOD = +1 | RISKY = -2
• Pickup > trip = -1 | Pickup >75% & >1mi = -0.5
==============================
"""

root = os.path.expanduser('~/Documents')
log_path = os.path.join(root, 'TripLog.txt')
push_path = os.path.join(root, 'TripPush.txt')

with open(log_path, 'a', encoding='utf-8') as f:
    f.write(block)
    f.flush()
    os.fsync(f.fileno())

push_content = (
    f'{status} | Score: {score}\n'
    f'⭐️{star_rating:.2f} | £/mi £{per_mile:.2f} | £/min £{per_min:.2f}'
)

with open(push_path, 'w', encoding='utf-8') as f:
    f.write(push_content)
    f.flush()
    os.fsync(f.fileno())
