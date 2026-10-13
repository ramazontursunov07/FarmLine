import logging

from django.db import transaction
from django.utils import timezone
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response
from rest_framework.throttling import ScopedRateThrottle
from rest_framework.views import APIView

from . import actions
from .context import build_context
from .models import PendingAction
from .services import AIError, chat

logger = logging.getLogger(__name__)

MAX_MESSAGE_LEN = 1000
MAX_HISTORY = 10
GENERIC_ERROR = "AI hozir javob bera olmadi. Birozdan keyin qayta urinib ko'ring."
ASK_CONFIRM = "Quyidagini bajaraymi? Tasdiqlasangiz, tizimga yozaman."
NOT_UNDERSTOOD = "Nima yozish kerakligini tushunmadim. Aniqroq ayting, masalan: «ombordan 50 kg omuxta yem chiqar»."


def answer_with_action(user, answer):
    """AI javobidagi harakat taklifini tekshirib, javob matni va (bo'lsa) tasdiq kartasini tuzadi."""
    text, raw = actions.extract_action(answer)
    if raw is None:
        return {'answer': text or NOT_UNDERSTOOD}

    pending, problems = actions.create_proposal(user, raw)
    notes = "\n".join(f"• {p}" for p in problems)
    if pending is None:
        if not problems:
            return {'answer': text or NOT_UNDERSTOOD}
        # Taklif yaroqsiz (mahsulot topilmadi, zaxira yetmaydi va h.k.): AI ning "tasdiqlang" deyishi noto'g'ri bo'lardi
        return {'answer': "Buni bajara olmayman:\n" + notes}
    # Karta server topgan ma'lumotdan tuziladi; AI matni o'rniga doim bir xil, aniq savol turadi
    body = ASK_CONFIRM + (("\n\nBajarib bo'lmaydiganlari:\n" + notes) if notes else "")
    return {'answer': body, 'action': actions.serialize_proposal(pending)}


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
            answer = chat(
                messages,
                build_context(request.user),
                extra_system=actions.build_action_prompt(request.user),
            )
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

        return Response(answer_with_action(request.user, answer))


class ActionConfirmView(APIView):
    """Foydalanuvchi AI taklifini tasdiqlaydi: amal oddiy API qoidalari bilan bajariladi."""
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        with transaction.atomic():
            # Qulf: tasdiqlash tugmasi ikki marta bosilsa ham amal bir marta bajariladi
            pending = PendingAction.objects.select_for_update().filter(pk=pk, user=request.user).first()
            if pending is None:
                return Response({'detail': "Amal topilmadi."}, status=404)
            code, body = actions.confirm(request, pending)
        return Response(body, status=code)


class ActionCancelView(APIView):
    permission_classes = [IsAuthenticated]

    def post(self, request, pk):
        updated = PendingAction.objects.filter(pk=pk, user=request.user, status='kutilmoqda').update(
            status='bekor', resolved_at=timezone.now()
        )
        if not updated and not PendingAction.objects.filter(pk=pk, user=request.user).exists():
            return Response({'detail': "Amal topilmadi."}, status=404)
        return Response({'detail': "Bekor qilindi"})
