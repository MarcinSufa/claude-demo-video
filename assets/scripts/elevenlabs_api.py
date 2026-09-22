"""elevenlabs_api.py -- ElevenLabs TTS/music HTTP client (stdlib only).

Pure functions (load_key, redact, alignment_to_words, tts_cache_key,
approval_code) have no side effects beyond the documented key lookup;
tts_request/music_request/ledger_append are the I/O boundary. Callers
(make-vo.py, make-music-elevenlabs.py, spend-gate.py) own all caching and
approval-gating -- this module only talks to the API and never persists a key.
"""
import base64
import hashlib
import json
import os
import re
import urllib.error
import urllib.request

API_BASE = "https://api.elevenlabs.io"

_KEY_LINE = re.compile(r"^\s*(?:export\s+)?ELEVENLABS_API_KEY\s*=\s*(.*?)\s*$")


class ElevenLabsError(Exception):
    pass


def _strip_quotes(v):
    if len(v) >= 2 and v[0] == v[-1] and v[0] in "\"'":
        return v[1:-1]
    return v


def _key_from_file(path):
    try:
        with open(path, encoding="utf-8") as f:
            lines = f.readlines()
    except OSError:
        return None
    for line in lines:
        m = _KEY_LINE.match(line.rstrip("\n"))
        if m:
            return _strip_quotes(m.group(1))
    return None


def load_key(env=None, root="."):
    env = os.environ if env is None else env
    direct = env.get("ELEVENLABS_API_KEY")
    if direct:
        return direct
    configured = env.get("DEMO_ELEVENLABS_ENV_FILE")
    if configured:
        return _key_from_file(configured)
    return _key_from_file(os.path.join(root, ".env"))


def redact(text, key):
    if not key:
        return text
    return text.replace(key, "<redacted>")


def alignment_to_words(alignment):
    chars = alignment.get("characters") if isinstance(alignment, dict) else None
    starts = alignment.get("character_start_times_seconds") if isinstance(alignment, dict) else None
    ends = alignment.get("character_end_times_seconds") if isinstance(alignment, dict) else None
    if not chars or not starts or not ends or not (len(chars) == len(starts) == len(ends)):
        raise ValueError(
            "alignment_to_words: characters/character_start_times_seconds/"
            "character_end_times_seconds must be non-empty and equal length")

    tokens = []
    cur_text, cur_start, cur_end = [], None, None
    for ch, s, e in zip(chars, starts, ends):
        if ch.isspace():
            if cur_text:
                tokens.append(("".join(cur_text), cur_start, cur_end))
                cur_text, cur_start = [], None
            continue
        if cur_start is None:
            cur_start = s
        cur_text.append(ch)
        cur_end = e
    if cur_text:
        tokens.append(("".join(cur_text), cur_start, cur_end))

    words, ends_list = [], []
    for text, start, end in tokens:
        is_punct = not any(c.isalnum() for c in text)
        if is_punct and words:
            words[-1]["text"] += text
            ends_list[-1] = end
        else:
            words.append({"text": text, "offset_sec": start})
            ends_list.append(end)
    for w, e in zip(words, ends_list):
        w["duration_sec"] = e - w["offset_sec"]
    return words


def tts_cache_key(voice_cfg, spoken_text):
    payload = {
        "provider": "elevenlabs",
        "voice_id": voice_cfg.get("voice_id"),
        "model_id": voice_cfg.get("model_id", "eleven_multilingual_v2"),
        "output_format": voice_cfg.get("output_format", "mp3_44100_128"),
        "language_code": voice_cfg.get("language_code"),
        "settings": voice_cfg.get("settings", {}),
        "text": spoken_text,
    }
    canonical = json.dumps(payload, sort_keys=True)
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()


def _post(url, key, body, timeout):
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data, method="POST",
        headers={"xi-api-key": key, "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read()
            headers = dict(resp.getheaders())
            return json.loads(raw.decode("utf-8")), headers
    except urllib.error.HTTPError as e:
        try:
            body_bytes = e.read()
        except Exception:
            body_bytes = b""
        msg = f"HTTP {e.code}: {body_bytes.decode('utf-8', 'replace')[:300]}"
        raise ElevenLabsError(redact(msg, key)) from None
    except urllib.error.URLError as e:
        raise ElevenLabsError(redact(str(e), key)) from None


def tts_request(key, voice_cfg, spoken_text, timeout=60):
    voice_id = voice_cfg["voice_id"]
    model_id = voice_cfg.get("model_id", "eleven_multilingual_v2")
    output_format = voice_cfg.get("output_format", "mp3_44100_128")
    language_code = voice_cfg.get("language_code")
    settings = voice_cfg.get("settings") or {}
    body = {"text": spoken_text, "model_id": model_id}
    if settings:
        body["voice_settings"] = settings
    if language_code:
        body["language_code"] = language_code
    url = f"{API_BASE}/v1/text-to-speech/{voice_id}/with-timestamps?output_format={output_format}"
    payload, headers = _post(url, key, body, timeout)
    audio = base64.b64decode(payload["audio_base64"])
    alignment = payload.get("alignment", {})
    return audio, alignment, headers


def music_request(key, composition_plan, model_id="music_v1",
                   output_format="mp3_44100_192", seed=None, timeout=300):
    body = {"composition_plan": composition_plan, "model_id": model_id}
    if seed is not None:
        body["seed"] = seed
    url = f"{API_BASE}/v1/music?output_format={output_format}"
    payload, headers = _post(url, key, body, timeout)
    audio = base64.b64decode(payload["audio_base64"])
    return audio, headers


def approval_code(uncached_keys, music_key):
    keys = sorted(set(uncached_keys or []))
    blob = "\n".join(keys) + "\nmusic:" + (music_key or "")
    return hashlib.sha256(blob.encode("utf-8")).hexdigest()[:8]


def ledger_append(root, record):
    path = os.path.join(root, ".spend-ledger.jsonl")
    with open(path, "a", encoding="utf-8") as f:
        f.write(json.dumps(record, sort_keys=True) + "\n")
