"""Vektor maydoni.

PostgreSQL da pgvector ning `vector(N)` turi, boshqa bazalarda (kompyuterdagi SQLite) oddiy matn (JSON) bo'lib
saqlanadi. Shunda migratsiyalar va testlar SQLite da ham ishlaydi; ma'no bo'yicha qidiruv esa faqat PostgreSQL da yoqiladi.
Qiymat Python da oddiy `list[float]`.
"""
import json

from django.db import models


class VectorField(models.Field):
    description = "Vektor (pgvector)"

    def __init__(self, *args, dimensions=None, **kwargs):
        self.dimensions = dimensions
        super().__init__(*args, **kwargs)

    def deconstruct(self):
        name, path, args, kwargs = super().deconstruct()
        if self.dimensions is not None:
            kwargs['dimensions'] = self.dimensions
        return name, path, args, kwargs

    def get_internal_type(self):
        return 'TextField'

    def db_type(self, connection):
        if connection.vendor == 'postgresql':
            return f'vector({self.dimensions})' if self.dimensions else 'vector'
        return 'text'

    def get_prep_value(self, value):
        value = super().get_prep_value(value)
        if value is None or isinstance(value, str):
            return value
        # pgvector matn ko'rinishi: [0.1,0.2,...]
        return json.dumps([float(x) for x in value], separators=(',', ':'))

    def get_placeholder(self, value, compiler, connection):
        # Parametr turi matn emas, vector ekanini aniq aytamiz (server tomonida bog'lashda ham ishlashi uchun)
        return '%s::vector' if connection.vendor == 'postgresql' else '%s'

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        if isinstance(value, str):
            return json.loads(value)
        return list(value)
