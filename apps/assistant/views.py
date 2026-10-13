import logging

from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from .context import build_context
from .services import AIError, chat

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 1000
MAX_HISTORY = 10
GENERIC_ERROR = "AI hozir javob bera olmadi. Birozdan keyin qayta urinib ko'ring."


def clean_history(raw):
    """Frontenddan kelgan suhbat tarixini tozalaydi: faqat to'g'ri formatdagi oxirgi xabarlar qoladi."""
    if not isinstance(raw, list):
        return []
    messages = []
    for item in raw[-MAX_HISTORY:]:
        if not isinstance(item, dict):
            continue
        role, content = item.get('role'), item.get('content')
        if role in ('user', 'assistant') and isinstance(content, str) and content.strip():
            messages.append({'role': role, 'content': content.strip()[:2000]})
    # Suhbat har doim foydalanuvchi xabaridan boshlanishi kerak
    while messages and messages[0]['role'] != 'user':
        messages.pop(0)
    return messages


class ChatView(APIView):
    permission_classes = [IsAuthenticated]
    throttle_classes = [ScopedRateThrottle]
    throttle_scope = 'assistant'  # AI so'rovlari pulli/limitli: bir foydalanuvchi ko'p yubora olmasin

    def post(self, request):
        text = (request.data.get('message') or '').strip()
        if not text:
            return Response({'detail': "Savol bo'sh bo'lmasligi kerak"}, status=400)
        if len(text) > MAX_MESSAGE_LEN:
            return Response({'detail': f"Savol juda uzun ({MAX_MESSAGE_LEN} belgigacha)"}, status=400)

        messages = clean_history(request.data.get('history'))
        messages.append({'role': 'user', 'content': text})

        try:
            answer = chat(messages, build_context(request.user))
        except AIError as exc:
            # Xatoning aniq sababi (kalit, limit va hokazo) faqat logda, foydalanuvchiga umumiy xabar
            logger.warning("AI xatosi: %s: %s", exc.__class__.__name__, exc)
            if getattr(exc, 'code', None) == 429:
                detail = "AI limiti tugadi. Birozdan keyin qayta urinib ko'ring."
            else:
                detail = GENERIC_ERROR
            return Response({'detail': detail}, status=502)
        except Exception:
            # Internet uzilishi va boshqa kutilmagan xatolar
            logger.exception("AI so'rovida kutilmagan xato")
            return Response({'detail': GENERIC_ERROR}, status=502)

        return Response({'answer': answer})
