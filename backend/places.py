
import threading
import time
import requests

# free api that biases results near princeton!

PHOTON_URL = 'https://photon.komoot.io/api/'
BIAS = {'lat': 40.3573, 'lon': -74.6672}
_CACHE_SECONDS = 3600
_CACHE_MAX = 500
_cache = {}
_lock = threading.Lock()


def _label(props):
    street = ' '.join(p for p in (props.get('housenumber'), props.get('street')) if p)
    parts = [props.get('name'), street, props.get('city') or props.get('county'),
             props.get('state')]
    seen, out = set(), []
    for part in parts:
        if part and part not in seen:
            seen.add(part)
            out.append(part)
    return ', '.join(out)


def search(query):
    """Return a list of suggestion strings for what the admin has typed so far."""
    query = ' '.join(query.split())[:200]
    if len(query) < 3:
        return []
    key = query.lower()
    now = time.time()
    with _lock:
        hit = _cache.get(key)
        if hit and now - hit[0] < _CACHE_SECONDS:
            return hit[1]
    try:
        response = requests.get(
            PHOTON_URL, params={'q': query, 'limit': 6, 'lang': 'en', **BIAS},
            headers={'User-Agent': 'roh-application/1.0'}, timeout=4)
        response.raise_for_status()
        features = response.json().get('features', [])
    except (requests.RequestException, ValueError):
        return []
    results = []
    for feature in features:
        label = _label(feature.get('properties') or {})[:300]
        if label and label not in results:
            results.append(label)
    with _lock:
        if len(_cache) >= _CACHE_MAX:
            _cache.clear()
        _cache[key] = (now, results)
    return results
