"""
Google Cloud Vision API wrapper for text detection on capture frames.

Deduplication logic (caller provides api_key + frame_path each call):
  1. Identical image bytes (same SHA-256) → skip, return cached result.
  2. New image → call Vision API.
  3. Compare detected text lines with previous result.
     Changed lines < TOLERANCE → treat as same scene, return cached.
     Changed lines >= TOLERANCE → fresh result, update cache.

TOLERANCE starts at 2 (even one changed line keeps cache; two lines = different scene).
Pure stdlib: json, hashlib, base64, urllib — no C extensions, pip-18 compatible.
"""
import os
import json
import time
import hashlib
import base64
import urllib.request
import urllib.error

TOLERANCE = 2   # min changed text lines to accept a fresh scan result

_VISION_URL = "https://vision.googleapis.com/v1/images:annotate?key=%s"

_state = {
    "last_hash":        None,
    "last_text_lines":  [],
    "last_result":      None,
    "last_translation": None,   # {text, source, lang, ts} — set by translate_last()
}


def _image_hash(data):
    return hashlib.sha256(data).hexdigest()[:20]


def _call_vision(image_bytes, api_key):
    payload = json.dumps({
        "requests": [{
            "image": {"content": base64.b64encode(image_bytes).decode()},
            "features": [{"type": "TEXT_DETECTION"}],
        }]
    }).encode()
    req = urllib.request.Request(
        _VISION_URL % api_key,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            return json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read())
            msg = body.get("error", {}).get("message", "") or str(exc)
        except Exception:
            msg = str(exc)
        raise RuntimeError("Vision API %d: %s" % (exc.code, msg))


def _parse_lines(vision_response):
    """Return logical text lines from Vision API response.
    ann[0] is the full composite block with newlines preserved — split that
    rather than ann[1:] which is individual word tokens (far too granular)."""
    try:
        ann = vision_response["responses"][0].get("textAnnotations", [])
        if not ann:
            return []
        return [ln.strip() for ln in ann[0]["description"].splitlines() if ln.strip()]
    except (KeyError, IndexError):
        return []


def scan_bytes(image_bytes, api_key):
    """Scan raw image bytes. Applies image-hash + text-line dedup vs the cache.
    Returns the same dict shape as scan()."""
    current_hash = _image_hash(image_bytes)

    # Identical bytes → never re-send.
    if current_hash == _state["last_hash"] and _state["last_result"] is not None:
        return dict(_state["last_result"], from_cache=True, skip_reason="identical_image")

    # New image → call Vision API.
    try:
        raw = _call_vision(image_bytes, api_key)
    except Exception as exc:
        return {"error": str(exc), "from_cache": False}

    new_lines = _parse_lines(raw)

    # Count symmetric diff of line sets vs previous result.
    old_set = set(_state["last_text_lines"])
    new_set = set(new_lines)
    changed = len(old_set.symmetric_difference(new_set))

    if changed < TOLERANCE and _state["last_result"] is not None:
        return dict(_state["last_result"], from_cache=True, skip_reason="low_change:%d" % changed)

    try:
        full_text = raw["responses"][0]["textAnnotations"][0]["description"]
    except (KeyError, IndexError):
        full_text = ""

    result = {
        "from_cache":    False,
        "text_lines":    new_lines,
        "full_text":     full_text,
        "changed_lines": changed,
        "scanned_at":    time.time(),
    }
    _state["last_hash"]       = current_hash
    _state["last_text_lines"] = new_lines
    _state["last_result"]     = result
    return result


_TRANSLATE_URL = "https://translation.googleapis.com/language/translate/v2?key=%s"


def translate(text, api_key, target="en"):
    """Translate text via Cloud Translation API v2. Returns {"translated": ..., "source": ...}
    or {"error": ...}. Pure stdlib — no C extensions."""
    payload = json.dumps({"q": text, "target": target, "format": "text"}).encode()
    req = urllib.request.Request(
        _TRANSLATE_URL % api_key,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=12) as resp:
            body = json.loads(resp.read())
        t = body["data"]["translations"][0]
        return {"translated": t["translatedText"], "source": t.get("detectedSourceLanguage", "")}
    except urllib.error.HTTPError as exc:
        try:
            body = json.loads(exc.read())
            msg = body.get("error", {}).get("message", "") or str(exc)
        except Exception:
            msg = str(exc)
        return {"error": "Translate API %d: %s" % (exc.code, msg)}
    except Exception as exc:
        return {"error": str(exc)}


def translate_last(api_key, target="en"):
    """Translate the cached scan text from the last scan_bytes() / scan() call.
    Stores result in _state["last_translation"] so /control/google/latest can
    deliver it to the frontend poll. Returns same shape as translate()."""
    last = _state.get("last_result")
    if not last:
        return {"error": "no scan in cache — scan an image first"}
    text = last.get("full_text") or "\n".join(last.get("text_lines", []))
    if not text:
        return {"error": "no text in last scan"}
    result = translate(text, api_key, target)
    if "translated" in result:
        _state["last_translation"] = {
            "text":   result["translated"],
            "source": result.get("source", ""),
            "lang":   target,
            "ts":     time.time(),
        }
    return result


def latest():
    """Snapshot of current cache state for frontend polling."""
    last = _state.get("last_result")
    return {
        "scan": {
            "lines": _state.get("last_text_lines", []),
            "ts":    last.get("scanned_at", 0),
        } if last else None,
        "translation": _state.get("last_translation"),
    }


def scan(image_path, api_key):
    """Load image_path and delegate to scan_bytes. Returns {"error": ...} if not found."""
    if not os.path.exists(image_path):
        return {"error": "no frame available", "from_cache": False}
    with open(image_path, "rb") as f:
        return scan_bytes(f.read(), api_key)
