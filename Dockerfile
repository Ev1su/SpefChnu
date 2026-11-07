FROM python:3.12-slim
RUN addgroup --system bot && adduser --system --ingroup bot bot
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY bot ./bot
RUN mkdir -p /app/data && chown -R bot:bot /app
USER bot
CMD ["python", "-m", "bot.main"]
