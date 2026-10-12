import json
import re

from django.db import IntegrityError, transaction
from rest_framework.exceptions import APIException, ParseError
from rest_framework.renderers import JSONRenderer
from rest_framework.response import Response

from .models import IdempotencyRecord

KEY_RE = re.compile(r'^[A-Za-z0-9_-]{8,64}$')


class RequestInProgress(APIException):
    status_code = 409
    default_detail = "Bu so'rov hozir bajarilmoqda, birozdan keyin qayta urinib ko'ring."


class IdempotentCreateMixin:
    """
    ViewSet'ning create() ini takrorlanishdan himoya qiladi.

    Mijoz `Idempotency-Key: <noyob qiymat>` sarlavhasini yuborsa:
    - birinchi marta: yozuv odatdagidek yaratiladi va javob saqlanadi;
    - xuddi shu kalit bilan qayta: yangi yozuv yaratilmaydi, birinchi javob qaytadi
      (`Idempotent-Replayed: true` sarlavhasi bilan).
    Xato bilan tugagan so'rovning kaliti band qilinmaydi: shart-sharoit o'zgarsa, qayta yuborish mumkin.
    Sarlavha bo'lmasa, hammasi avvalgidek ishlaydi.
    """

    def create(self, request, *args, **kwargs):
        key = request.headers.get('Idempotency-Key')
        if not key:
            return super().create(request, *args, **kwargs)
        if not KEY_RE.match(key):
            raise ParseError("Idempotency-Key 8-64 ta belgidan iborat bo'lishi va faqat harf, raqam, '-' yoki '_' "
                             "ishlatishi kerak.")

        try:
            # Kalitni yozuv bilan BIR tranzaksiyada band qilamiz: bir vaqtda kelgan ikkinchi so'rov
            # birinchisi tugaguncha kutadi, keyin IntegrityError oladi va saqlangan javobni qaytaradi.
            with transaction.atomic():
                record = IdempotencyRecord.objects.create(user=request.user, key=key, path=request.path)
                response = super().create(request, *args, **kwargs)
                record.status_code = response.status_code
                record.response_body = json.loads(JSONRenderer().render(response.data))
                record.save(update_fields=['status_code', 'response_body'])
                return response
        except IntegrityError:
            record = IdempotencyRecord.objects.filter(user=request.user, key=key).first()
            if record is None:
                raise  # bu kalit bilan bog'liq emas, boshqa muammo
            if record.path != request.path:
                raise ParseError("Bu kalit boshqa so'rov uchun ishlatilgan.")
            if record.status_code is None:
                raise RequestInProgress()
            return Response(record.response_body, status=record.status_code,
                            headers={'Idempotent-Replayed': 'true'})
