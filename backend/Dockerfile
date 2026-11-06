FROM python:3.12-slim
# Docker command-line tool, used by the grade worker to start sandbox containers.
COPY --from=docker:27-cli /usr/local/bin/docker /usr/local/bin/docker
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FLASK_APP=wsgi.py
# Apply database migrations, then serve the API.
# One process with threads, so the in-memory rate limits are shared by all requests.
CMD ["sh", "-c", "flask db upgrade && gunicorn -w 1 --threads 8 -b 0.0.0.0:5000 wsgi:app"]
