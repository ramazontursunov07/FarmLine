"""AI provayderlar bilan ishlash. Provayder .env dagi AI_PROVIDER bilan tanlanadi:

    gemini  (standart)  -- GEMINI_API_KEY kerak
    openai              -- OpenAI-mos API (Groq, OpenRouter va h.k.): AI_API_KEY, AI_BASE_URL kerak
"""
import requests
from django.conf import settings

SYSTEM = (
    "Sen FarmLine fermer yordamchisisan. "
    "O'zbek tilida, qisqa va tushunarli javob ber. "
    "Ob-havo haqida so'ralsa, quyida berilgan ob-havo ma'lumotidan foydalanib javob ber va "
    "chorva uchun qisqa maslahat qo'sh. "
    "Ferma raqamlari so'ralsa (omborda qancha sut yoki yem bor, qancha sut sog'ildi yoki sotildi, "
    "kirim-chiqim, foyda, qarzlar), quyidagi ma'lumotdan mos qatorni topib, raqamni AYNAN o'sha yerdan ol "
    "va davrni aniq ayt (bugun, kecha, oxirgi 7 kun, shu oy, o'tgan oy, shu yil yoki alohida oy/kun). "
    "Bir nechta ferma bo'lsa, har bir ferma uchun alohida ayt. "
    "So'ralgan davr yoki ma'lumot ro'yxatda bo'lmasa, o'ylab topma va hisoblab chiqarma: nima yo'qligini ayt "
    "va saytdagi tegishli bo'limni (Moliya, Ombor, Sut, Qarzlar) ko'rsat."
)

EMPTY_ANSWER = "Javob olinmadi. Savolni boshqacha yozib ko'ring."

DEFAULT_MODELS = {
    'gemini': 'gemini-flash-latest',
    'openai': 'openai/gpt-oss-120b',  # Groq uchun; OpenRouter'da AI_MODEL ni o'zingiz yozasiz
}
DEFAULT_BASE_URL = 'https://api.groq.com/openai/v1'
TIMEOUT = 50


class AIError(Exception):
    """Provayderdan kelgan xato. code -- HTTP holati (masalan 429 = limit tugadi)."""

    def __init__(self, message, code=None):
        super().__init__(message)
        self.code = code


def build_system(context='', extra=''):
    """extra -- qo'shimcha ko'rsatma (masalan, AI harakatlari qoidalari): ferma holatidan keyin qo'shiladi."""
    system = SYSTEM
    if context:
        system += (
            "\n\nFoydalanuvchining hozirgi ferma holati (faqat shu ma'lumotga tayan, "
            "raqamlarni o'ylab topma; ma'lumot yetmasa, shuni ayt):\n"
            + context
        )
    if extra:
        system += "\n\n" + extra
    return system


def _model(provider):
    return getattr(settings, 'AI_MODEL', None) or DEFAULT_MODELS[provider]


def _chat_gemini(messages, system):
    from google import genai
    from google.genai import errors as genai_errors, types

    client = genai.Client(api_key=settings.GEMINI_API_KEY)
    # Gemini'da AI roli "assistant" emas, "model" deb ataladi
    contents = [
        types.Content(
            role='model' if m['role'] == 'assistant' else 'user',
            parts=[types.Part(text=m['content'])],
        )
        for m in messages
    ]
    try:
        response = client.models.generate_content(
            model=_model('gemini'),
            contents=contents,
            config=types.GenerateContentConfig(system_instruction=system, max_output_tokens=2000),
        )
    except genai_errors.APIError as exc:
        raise AIError(str(exc), code=getattr(exc, 'code', None)) from exc
    return response.text or ''


def _chat_openai(messages, system):
    base_url = (getattr(settings, 'AI_BASE_URL', None) or DEFAULT_BASE_URL).rstrip('/')
    payload = {
        'model': _model('openai'),
        'messages': [{'role': 'system', 'content': system}] + messages,
        'max_tokens': 4000,  # fikrlovchi modellarda "o'ylash" tokenlari ham shu limitga kiradi
    }
    headers = {'Authorization': f"Bearer {settings.AI_API_KEY}"}
    try:
        resp = requests.post(f"{base_url}/chat/completions", json=payload, headers=headers, timeout=TIMEOUT)
    except requests.RequestException as exc:
        raise AIError(str(exc)) from exc
    if resp.status_code != 200:
        raise AIError(resp.text[:300], code=resp.status_code)
    try:
        return resp.json()['choices'][0]['message']['content'] or ''
    except (KeyError, IndexError, TypeError, ValueError) as exc:
        raise AIError("Provayderdan kutilmagan javob formati") from exc


PROVIDERS = {'gemini': _chat_gemini, 'openai': _chat_openai}


def chat(messages, context='', extra_system=''):
    provider = (getattr(settings, 'AI_PROVIDER', None) or 'gemini').lower()
    if provider not in PROVIDERS:
        raise AIError(f"Noma'lum AI_PROVIDER: {provider}")
    answer = PROVIDERS[provider](messages, build_system(context, extra_system))
    return answer.strip() or EMPTY_ANSWER
