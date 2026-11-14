FROM python:3.12-slim-bookworm
RUN pip install --no-cache-dir discord.py==2.4.0 docker==7.1.0
COPY worker.py /app/worker.py
CMD ["python3", "-u", "/app/worker.py"]
