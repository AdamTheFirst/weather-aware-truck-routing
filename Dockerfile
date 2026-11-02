# One image that builds the React app and serves it + the API from Django.

# --- build the frontend
FROM node:22-alpine AS web
WORKDIR /web
COPY frontend/package*.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build

# --- python app
FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_DEBUG=0
WORKDIR /app/backend
COPY backend/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY backend/ ./
# Django warns on every request if STATIC_ROOT does not exist yet.
RUN mkdir -p staticfiles
COPY --from=web /web/dist /app/frontend/dist
EXPOSE 8000
# One worker so the in-process cache is shared. Threads cover the wait on
# the weather and routing APIs. $PORT is set by Render; 8000 is the local default.
CMD gunicorn config.wsgi:application --bind 0.0.0.0:${PORT:-8000} --workers 1 --threads 8 --timeout 60
