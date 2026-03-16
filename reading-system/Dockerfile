FROM python:3.11-slim
WORKDIR /app
RUN pip install --no-cache-dir requests
COPY flashcard_server.py flashcards_app.html flashcards.html sm2.py ./
CMD ["python3", "flashcard_server.py"]
