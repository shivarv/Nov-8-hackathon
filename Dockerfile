# One image for deployment (Render): the built frontend, served by the backend that
# also answers /api. Local development keeps using docker-compose.yml / Vite.
#
#   docker build -t better-basket . && docker run -p 8000:8000 better-basket

# --- 1. build the frontend ------------------------------------------------------------
FROM node:20-alpine AS frontend
WORKDIR /frontend
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- 2. the backend, serving the build ------------------------------------------------
FROM python:3.12-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    FRONTEND_DIST=/app/frontend/dist \
    DATA_SOURCE=instacart

WORKDIR /app/backend
COPY backend/requirements.txt .
RUN pip install -r requirements.txt

COPY backend/ ./
# data/: the pre-built seed (catalog + orders, ~1 MB), photos and demo shoppers
COPY data/ /app/data/
COPY --from=frontend /frontend/dist /app/frontend/dist

EXPOSE 8000
# Render sets $PORT; default to 8000 elsewhere.
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
