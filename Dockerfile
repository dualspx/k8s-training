FROM python:3.12-slim
WORKDIR /app
COPY pyproject.toml README.md ./
COPY cka_game ./cka_game
RUN pip install --no-cache-dir .
ENV CKA_GAME_ROOT=/app
EXPOSE 8000
CMD ["cka-game", "serve", "--host", "0.0.0.0", "--port", "8000"]
