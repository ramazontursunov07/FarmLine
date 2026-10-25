"""Ob-havo: Open-Meteo (bepul, kalit kerak emas). Ferma manzili -> koordinata -> 7 kunlik prognoz."""
import logging

import requests
from django.core.cache import cache
from django.utils import timezone

logger = logging.getLogger(__name__)

GEOCODE_URL = 'https://geocoding-api.open-meteo.com/v1/search'
FORECAST_URL = 'https://api.open-meteo.com/v1/forecast'
TIMEOUT = 8
CACHE_SECONDS = 60 * 60       # shuncha vaqt ichida Open-Meteo'dan qayta so'ramaymiz (429 "juda ko'p so'rov" bo'lmasin)
STALE_SECONDS = 24 * 60 * 60  # xizmat javob bermasa, shuncha vaqt eski natijani ko'rsatamiz

# Ogohlantirish chegaralari
FROST_C = 0          # min harorat shundan past yoki teng bo'lsa
HEAT_C = 35          # max harorat shundan yuqori yoki teng bo'lsa
WIND_KMH = 40        # shamol (km/soat)
RAIN_MM = 10         # bir kunlik yog'in (mm)

WEATHER_TEXT = {
    0: 'Ochiq', 1: 'Asosan ochiq', 2: 'Qisman bulutli', 3: 'Bulutli',
    45: 'Tuman', 48: 'Tuman',
    51: "Mayda yog'in", 53: "Mayda yog'in", 55: "Mayda yog'in",
    56: "Muzlovchi yog'in", 57: "Muzlovchi yog'in",
    61: 'Yomg\'ir', 63: 'Yomg\'ir', 65: "Kuchli yomg'ir",
    66: "Muzlovchi yomg'ir", 67: "Muzlovchi yomg'ir",
    71: 'Qor', 73: 'Qor', 75: "Kuchli qor", 77: 'Qor',
    80: "Jala", 81: "Jala", 82: "Kuchli jala",
    85: 'Qor', 86: "Kuchli qor",
    95: "Momaqaldiroq", 96: "Momaqaldiroq, do'l", 99: "Momaqaldiroq, do'l",
}


class WeatherError(Exception):
    pass


def weather_text(code):
    return WEATHER_TEXT.get(code, '')


def _get_json(url, params):
    try:
        r = requests.get(url, params=params, timeout=TIMEOUT)
        r.raise_for_status()
        return r.json()
    except (requests.RequestException, ValueError) as exc:
        logger.warning('Open-Meteo xatosi: %s', exc)
        raise WeatherError("Ob-havo xizmatiga ulanib bo'lmadi") from exc


def _candidates(location):
    """'Qarshi tumani, Qashqadaryo' -> to'liq matn, keyin vergul bilan ajratilgan bo'laklar."""
    text = (location or '').strip()
    out = [text] if text else []
    for part in text.split(','):
        part = part.strip()
        if part and part not in out:
            out.append(part)
    return out


def geocode(location):
    """(latitude, longitude) yoki None."""
    for name in _candidates(location):
        data = _get_json(GEOCODE_URL, {'name': name, 'count': 1, 'language': 'uz', 'format': 'json'})
        results = data.get('results') or []
        if results:
            return float(results[0]['latitude']), float(results[0]['longitude'])
    return None


def fetch_forecast(lat, lon):
    key = f'weather:{round(lat, 2)}:{round(lon, 2)}'
    cached = cache.get(key)
    if cached:
        return cached
    try:
        data = _get_json(FORECAST_URL, {
            'latitude': lat, 'longitude': lon, 'timezone': 'auto', 'forecast_days': 7,
            'current': 'temperature_2m,relative_humidity_2m,wind_speed_10m,weather_code',
            'daily': ('weather_code,temperature_2m_max,temperature_2m_min,'
                      'precipitation_sum,precipitation_probability_max,wind_speed_10m_max'),
        })
    except WeatherError:
        # Xizmat javob bermadi: bo'sh xato o'rniga oxirgi muvaffaqiyatli natijani "eskirgan" belgisi bilan beramiz
        stale = cache.get(key + ':stale')
        if stale:
            return {**stale, 'stale': True}
        raise
    result = parse_forecast(data)
    result['updated_at'] = timezone.now().isoformat()
    cache.set(key, result, CACHE_SECONDS)
    cache.set(key + ':stale', result, STALE_SECONDS)
    return result


def _r(value):
    return None if value is None else round(value, 1)


def parse_forecast(data):
    cur = data.get('current') or {}
    d = data.get('daily') or {}
    days = []
    for i, date in enumerate(d.get('time') or []):
        def pick(name, i=i):
            vals = d.get(name) or []
            return vals[i] if i < len(vals) else None
        code = pick('weather_code')
        days.append({
            'date': date,
            'temp_max': _r(pick('temperature_2m_max')),
            'temp_min': _r(pick('temperature_2m_min')),
            'rain_mm': _r(pick('precipitation_sum')),
            'rain_chance': pick('precipitation_probability_max'),
            'wind_kmh': _r(pick('wind_speed_10m_max')),
            'code': code,
            'text': weather_text(code),
        })
    code = cur.get('weather_code')
    return {
        'current': {
            'temp': _r(cur.get('temperature_2m')),
            'humidity': cur.get('relative_humidity_2m'),
            'wind_kmh': _r(cur.get('wind_speed_10m')),
            'code': code,
            'text': weather_text(code),
        },
        'days': days,
    }


def farm_weather_context(farm):
    """AI yordamchi uchun ob-havo matni (xato bo'lsa None: yordamchi ob-havosiz ham ishlayveradi)."""
    try:
        if farm.latitude is None or farm.longitude is None:
            point = geocode(farm.location)
            if point is None:
                return None
            farm.latitude, farm.longitude = point
            farm.save(update_fields=['latitude', 'longitude'])
        fc = fetch_forecast(farm.latitude, farm.longitude)
    except WeatherError:
        return None
    cur = fc['current']
    lines = [f"Ob-havo ({farm.name}, {farm.location}): hozir {cur['temp']}°, {cur['text']}, "
             f"shamol {cur['wind_kmh']} km/soat, namlik {cur['humidity']}%"]
    for d in fc['days']:
        rain = f", yog'in {d['rain_mm']} mm ({d['rain_chance']}%)" if d['rain_mm'] else ''
        lines.append(f"  • {d['date']}: {d['temp_min']}…{d['temp_max']}°, {d['text']}, "
                     f"shamol {d['wind_kmh']} km/soat{rain}")
    for a in build_alerts(fc['days']):
        lines.append(f"  ! {a['date']}: {a['text']}")
    return "\n".join(lines)


def build_alerts(days):
    """Dehqon uchun qisqa ogohlantirishlar (eng yaqin kunlar bo'yicha)."""
    alerts = []
    for day in days:
        date = day['date']
        tmin, tmax, wind, rain = day['temp_min'], day['temp_max'], day['wind_kmh'], day['rain_mm']
        if tmin is not None and tmin <= FROST_C:
            alerts.append({'type': 'frost', 'date': date, 'level': 'danger',
                           'text': f"Sovuq: {tmin:g}°. Yosh mollar va suv quvurlarini isiting, qo'shimcha to'shama va issiq suv bering."})
        if tmax is not None and tmax >= HEAT_C:
            alerts.append({'type': 'heat', 'date': date, 'level': 'danger',
                           'text': f"Jazirama: {tmax:g}°. Soya va ko'proq toza suv bering, mollarni kunduzi haydamang."})
        if wind is not None and wind >= WIND_KMH:
            alerts.append({'type': 'wind', 'date': date, 'level': 'warn',
                           'text': f"Kuchli shamol: {wind:g} km/soat. Tom, to'siq va yengil buyumlarni mahkamlang."})
        if rain is not None and rain >= RAIN_MM:
            alerts.append({'type': 'rain', 'date': date, 'level': 'warn',
                           'text': f"Kuchli yog'in: {rain:g} mm. Yemni quruq saqlang, molxona va yo'llarni tekshiring."})
    return alerts[:6]
