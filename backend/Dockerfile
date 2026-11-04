FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
ENV FLASK_APP=wsgi.py
# Apply database migrations, then serve the API.
CMD ["sh", "-c", "flask db upgrade && gunicorn -w 2 -b 0.0.0.0:5000 wsgi:app"]
