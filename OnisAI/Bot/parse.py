# OCR text parsing + contextual pickup classification

import re


def sanity_basic(ocr_text: str):
    """
    Minimal sanity gate used during OCR retries.
    Returns (sane, main_price, pickup_min, pickup_miles, trip_min, trip_miles)
    """
    price_matches = re.findall(r'£\s*(\d+\.\d+)', ocr_text)
    fares = [float(p) for p in price_matches if float(p) > 2.00]
    main_price = max(fares) if fares else 0.0

    def _parse_hr_min(text):
        hr = re.search(r'(\d+)\s*hr', text)
        mi = re.search(r'(\d+)\s*mins?', text)
        h = int(hr.group(1)) if hr else 0
        m = int(mi.group(1)) if mi else 0
        return h * 60 + m

    pairs = re.findall(r'((?:\d+\s*hr\s*)?\d+\s*mins?)[^\n]*\((\d+(\.\d+)?)\s*mi\)', ocr_text)
    pickup_min = _parse_hr_min(pairs[0][0]) if len(pairs) >= 1 else 0
    pickup_miles = float(pairs[0][1]) if len(pairs) >= 1 else 0.0
    trip_min = _parse_hr_min(pairs[1][0]) if len(pairs) >= 2 else 0
    trip_miles = float(pairs[1][1]) if len(pairs) >= 2 else 0.0

    sane = (
        main_price > 0 and
        trip_min > 0 and trip_miles > 0 and
        pickup_min >= 0 and pickup_miles >= 0 and
        trip_min <= 240 and trip_miles <= 150
    )
    return sane, main_price, pickup_min, pickup_miles, trip_min, trip_miles


def parse_card(ocr_text: str):
    """
    Extract main_price, star_rating, pickup_min, pickup_miles, trip_min, trip_miles
    (keeps your original patterns)
    """
    price_matches = re.findall(r'£\s*(\d+\.\d+)', ocr_text)
    fares = [float(p) for p in price_matches if float(p) > 2.00]
    main_price = max(fares) if fares else 0.0

    star_rating = 0.0
    for line in ocr_text.splitlines():
        if '£' in line:
            continue
        m = re.search(r'(\d\.\d{2})', line)
        if m:
            star_rating = float(m.group(1))
            break

    def parse_hr_min(text):
        hr = re.search(r'(\d+)\s*hr', text)
        mi = re.search(r'(\d+)\s*mins?', text)
        h = int(hr.group(1)) if hr else 0
        m = int(mi.group(1)) if mi else 0
        return h * 60 + m

    pairs = re.findall(r'((?:\d+\s*hr\s*)?\d+\s*mins?)[^\n]*\((\d+(\.\d+)?)\s*mi\)', ocr_text)
    pickup_min, pickup_miles = (parse_hr_min(pairs[0][0]), float(pairs[0][1])) if len(pairs) >= 1 else (0, 0.0)
    trip_min, trip_miles     = (parse_hr_min(pairs[1][0]), float(pairs[1][1])) if len(pairs) >= 2 else (0, 0.0)

    return main_price, star_rating, pickup_min, pickup_miles, trip_min, trip_miles


def pickup_status_ctx(pmiles: float, pmins: int, tmiles: float, tmins: int) -> str:
    """
    Classify pickup proximity based on trip length/duration.
    """
    if tmiles >= 10 or tmins >= 25:
        band = 'long'
    elif tmiles >= 5 or tmins >= 10:
        band = 'medium'
    else:
        band = 'short'

    if band == 'short':
        if pmiles <= 1.0 and pmins <= 5:
            return "CLOSE"
        elif pmiles <= 1.5 or pmins <= 8:
            return "⚠️ SLIGHTLY FAR"
        else:
            return "❌ TOO FAR"
    elif band == 'medium':
        if pmiles <= 1.5 and pmins <= 8:
            return "CLOSE"
        elif pmiles <= 2.0 or pmins <= 10:
            return "⚠️ SLIGHTLY FAR"
        else:
            return "❌ TOO FAR"
    else:  # long
        if pmiles <= 2.5 and pmins <= 10:
            return "CLOSE"
        elif pmiles <= 3.5 or pmins <= 14:
            return "⚠️ SLIGHTLY FAR"
        else:
            return "❌ TOO FAR"


# ------------------------------ NEW: Address extraction (first/second time+mi anchors) ------------------------------

# Recognize "time + (miles)" lines (covers hr/hrs/hours; min/mins/minutes; decimal miles)
_TIME_DIST_RE = re.compile(
    r'(?P<time>(?:\d+\s*(?:hr|hrs|hour|hours)\s*)?\d+\s*(?:min|mins|minute|minutes))'
    r'[^\n]*?'
    r'\(\s*(?P<miles>\d+(?:\.\d+)?)\s*mi\s*\)',
    re.I
)

# UK postcode stopper + GB/UK tokens
_UK_PC_RE = re.compile(r'\b([A-Z]{1,2}\d{1,2}[A-Z]?)\s*([0-9][A-Z]{2})\b', re.I)
_COUNTRY_TOKENS = (' GB', ' UK', ' gb', ' uk')

# Uber overlay junk that can appear after addresses on the card
_OVERLAY_STOPWORDS = (
    'Confirm', 'Towards your destination', 'a Long trip',
    'Exclusive', 'Priority', 'Match', 'PIN', '4*', '5*',
    'fast charger', 'Fast charger', 'From stack', 'Reserve'
)

_SECTION_MARKERS_RE = re.compile(r'^(🔋|📍|🏁|🚗|💰|⭐|🛣|⏱|📏|💸|STATUS|⚠️|——————)\b')
_BULLET_RE = re.compile(r'^[•\-\u2022]\s*')


def _mild_normalise(s: str) -> str:
    # Fix a few recurrent OCR slips only
    s = re.sub(r'\bPI\b', 'Pl', s)   # Place
    s = re.sub(r'\bWIG\b', 'W1G', s) # London W1G district
    return s


def _truncate_at_terminal(s: str) -> str:
    """Cut the line right after a UK postcode or a GB/UK token; else return as-is."""
    m = _UK_PC_RE.search(s)
    if m:
        return s[:m.end()].rstrip(' ,.;-')
    for tok in _COUNTRY_TOKENS:
        pos = s.find(tok)
        if pos != -1:
            return s[:pos + len(tok)].rstrip(' ,.;-')
    return s


def _strip_overlays(s: str) -> str:
    for w in _OVERLAY_STOPWORDS:
        pos = s.find(w)
        if pos != -1:
            s = s[:pos]
            break
    return s.rstrip(' ,.;-')


def _clean_addr_line(s: str) -> str:
    s = _truncate_at_terminal(s)
    s = _strip_overlays(s)
    s = _mild_normalise(s)
    return s


def _collect_address_from(lines, start_idx, stop_on_trip_word=False):
    """
    Begin from the *next* line after start_idx and collect address lines.
    Stop when:
      - blank line or section marker
      - the word 'trip' appears (only if stop_on_trip_word=True; used for pickup parsing)
      - we hit a terminal (UK postcode or GB/UK token)
      - line begins with overlay word (Confirm/fast charger/etc.)
    """
    out = []
    i = start_idx + 1
    while i < len(lines):
        raw = lines[i]
        s = _BULLET_RE.sub('', raw).strip()
        if not s:
            break
        if _SECTION_MARKERS_RE.search(s):
            break
        if stop_on_trip_word and re.search(r'\btrip\b', s, re.I):
            break
        if any(s.startswith(w) for w in _OVERLAY_STOPWORDS) or s.lower().startswith('a long trip'):
            break

        cleaned = _clean_addr_line(s)
        if cleaned:
            out.append(cleaned)

        # If this line had a terminal, we included it—now stop collecting.
        if _UK_PC_RE.search(s) or any(tok in s for tok in _COUNTRY_TOKENS):
            break

        i += 1

    addr = " ".join(out)
    addr = re.sub(r"\s+", " ", addr).strip(" ,.;-")
    return addr


def _first_two_time_distance_indices(text: str):
    """Return (lines, [row_index_of_first, row_index_of_second]) for time+mi matches."""
    lines = text.splitlines()
    rows = []
    for idx, ln in enumerate(lines):
        if _TIME_DIST_RE.search(ln):
            rows.append(idx)
            if len(rows) == 2:
                break
    return lines, rows


def extract_pickup_address(ocr_text: str) -> str:
    """
    PICKUP = address lines immediately after the FIRST time–distance row.
    Fallback: if no pair found, look for 'away' row then collect.
    """
    lines, rows = _first_two_time_distance_indices(ocr_text)
    if rows:
        return _collect_address_from(lines, rows[0], stop_on_trip_word=True) or 'Unknown'

    # Fallback to 'away'
    for idx, ln in enumerate(lines):
        if re.search(r'\baway\b', ln, re.I):
            return _collect_address_from(lines, idx, stop_on_trip_word=True) or 'Unknown'
    return 'Unknown'


def extract_dropoff_address(ocr_text: str) -> str:
    """
    DROPOFF = address lines immediately after the SECOND time–distance row.
    Fallback: if no second pair, look for 'trip' row then collect.
    """
    lines, rows = _first_two_time_distance_indices(ocr_text)
    if len(rows) >= 2:
        return _collect_address_from(lines, rows[1], stop_on_trip_word=False) or 'Unknown'

    # Fallback to 'trip'
    for idx, ln in enumerate(lines):
        if re.search(r'\btrip\b', ln, re.I):
            return _collect_address_from(lines, idx, stop_on_trip_word=False) or 'Unknown'
    return 'Unknown'


def parse_addresses(ocr_text: str):
    """
    Convenience wrapper → (pickup_address, dropoff_address)
    """
    return extract_pickup_address(ocr_text), extract_dropoff_address(ocr_text)
