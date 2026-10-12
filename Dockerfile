# 1-bosqich: React ilovasini yig'ish (frontend/dist)
FROM node:22-slim AS frontend
WORKDIR /app/frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# 2-bosqich: Django (frontend/dist ham shu ichida beriladi)
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1
WORKDIR /app
COPY requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
COPY --from=frontend /app/frontend/dist ./frontend/dist
RUN sed -i 's/\r$//' start.sh && chmod +x start.sh \
    && SECRET_KEY=build-only python manage.py collectstatic --noinput
CMD ["./start.sh"]
