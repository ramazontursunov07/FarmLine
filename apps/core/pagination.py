from rest_framework.pagination import LimitOffsetPagination


class OptionalLimitOffsetPagination(LimitOffsetPagination):
    """
    ?limit= berilmasa, ro'yxat avvalgidek to'liq (massiv) qaytadi, shuning uchun mavjud sahifalar buzilmaydi.
    ?limit=200&offset=0 berilsa: {"count": ..., "next": ..., "previous": ..., "results": [...]}.
    Yozuvlari ko'payadigan ro'yxatlarni (hodisalar, ombor harakatlari, vazifalar) frontend limit bilan so'raydi.
    """
    default_limit = None
    max_limit = 1000
