"""Ovozli xabarni matnga aylantirish (Telegram bot uchun).

Provayder .env dagi STT_PROVIDER bilan tanlanadi (bo'sh bo'lsa, AI_PROVIDER bilan bir xil):

    gemini  -- GEMINI_API_KEY kerak (o'zbek tilini yaxshi tushunadi)
    openai  -- OpenAI-mos /audio/transcriptions (Groq whisper-large-v3 va h.k.): AI_API_KEY, AI_BASE_URL kerak

Aytilgan gap hech qachon to'g'ridan-to'g'ri bajarilmaydi: matn botda foydalanuvchiga ko'rsatiladi va
oddiy AI + «Tasdiqlash» tizimidan o'tadi, shuning uchun noto'g'ri tushunilgan ovoz ham xavfsiz.
"""
import requests
from django.conf import settings

from .services import AIError, DEFAULT_BASE_URL

TIMEOUT = 60
MAX_AUDIO_BYTES = 5 * 1024 * 1024  # Telegram ovozli xabari odatda 1 MB dan kichik

DEFAULT_STT_MODELS = {
    'gemini': 'gemini-flash-latest',
    'openai': 'whisper-large-v3',  # Groq uchun
}

# Fermer so'zlarini to'g'ri eshitishi uchun maslahat (Whisper "prompt", Gemini ko'rsatmasi)
HINT = ("Fermer ovozli xabari, o'zbek tilida: sigir, buzoq, litr, sut, kg, qop, omuxta yem, ombor, so'm, "
        "ertalab, kechqurun, bugun, kecha.")

GEMINI_PROMPT = (
        "Bu o'zbek tilidagi (ba'zan ruscha so'zlar aralash) qisqa ovozli xabar. "
        "Aytilgan gapni AYNAN matnga yoz: o'zgartirma, qo'shma, tushuntirma. "
        "Raqamlarni raqam bilan yoz (masalan «85 litr»). Faqat matnning o'zini qaytar. "
        "Ovozda hech narsa aytilmagan yoki tushunarsiz bo'lsa, bo'sh javob qaytar. " + HINT
)


def _provider():
    provider = (getattr(settings, 'STT_PROVIDER', None) or getattr(settings, 'AI_PROVIDER', None) or 'gemini').lower()
    if provider not in ('gemini', 'openai'):
        raise AIError(f"Noma'lum STT_PROVIDER: {provider}")
    return provider


def _model(provider):
    return getattr(settings, 'STT_MODEL', None) or DEFAULT_STT_MODELS[provider]


def _transcribe_gemini(audio, mime_type):
    from google import genai
    from google.genai import errors as genai_errors, types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    try:
        response = client.models.generate_content(
            model=_model('gemini'),
            contents=[types.Part.from_bytes(data=audio, mime_type=mime_type), GEMINI_PROMPT],
            config=types.GenerateContentConfig(max_output_tokens=1000),
        )
    except genai_errors.APIError as exc:
        raise AIError(str(exc), code=getattr(exc, 'code', None)) from exc
    return response.text or ''


def _transcribe_openai(audio, mime_type):
    base_url = (getattr(settings, 'AI_BASE_URL', None) or DEFAULT_BASE_URL).rstrip('/')
    headers = {'Authorization': f"Bearer {settings.AI_API_KEY}"}
    try:
        resp = requests.post(
            f"{base_url}/audio/transcriptions",
            headers=headers,
            files={'file': ('voice.ogg', audio, mime_type)},
            data={'model': _model('openai'), 'language': 'uz', 'prompt': HINT, 'response_format': 'json'},
            timeout=TIMEOUT,
        )
    except requests.RequestException as exc:
        raise AIError(str(exc)) from exc
    if resp.status_code != 200:
        raise AIError(resp.text[:300], code=resp.status_code)
    try:
        return resp.json().get('text') or ''
    except ValueError as exc:
        raise AIError("Provayderdan kutilmagan javob formati") from exc


def transcribe(audio, mime_type='audio/ogg'):
    """Ovoz baytlarini matnga aylantiradi. Tanib bo'lmasa AIError ko'taradi."""
    if not audio:
        raise AIError("Ovoz bo'sh")
    if len(audio) > MAX_AUDIO_BYTES:
        raise AIError("Ovoz fayli juda katta")
    provider = _provider()
    text = (_transcribe_gemini if provider == 'gemini' else _transcribe_openai)(audio, mime_type)
    text = (text or '').strip().strip('"«»').strip()
    if not text:
        raise AIError("Ovozdan matn chiqmadi")
    return text
