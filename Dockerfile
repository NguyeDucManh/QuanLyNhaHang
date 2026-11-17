# Debian 12 matches Render's documented native OS; the image owns its OS deps.
FROM python:3.14.8-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1 DJANGO_DEBUG=false \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MALLOC_ARENA_MAX=2 PORT=10000
WORKDIR /app
RUN apt-get update && apt-get install -y --no-install-recommends \
    libegl1 libgles2 libgl1 libglib2.0-0 libportaudio2 libgomp1 \
    && rm -rf /var/lib/apt/lists/*
COPY . /app
# Build has no database or live credential. Never declare sensitive Render
# environment variables as build ARG/ENV or bake them into the image.
RUN DJANGO_SECRET_KEY=container-build-only-not-a-live-secret-0123456789 \
    DJANGO_SETTINGS_MODULE=restaurant_system.settings DJANGO_DEBUG=false \
    RENDER=false DATABASE_URL='' DB_HOST=127.0.0.1 DB_NAME=build_only \
    DB_USER=build_only DB_PASSWORD=build-only-unused \
    bash build.sh \
    && python -m pip check \
    && useradd --create-home --uid 10001 restaurant \
    && chown -R restaurant:restaurant /app
USER restaurant
EXPOSE 10000
CMD ["bash", "scripts/start_render.sh"]
