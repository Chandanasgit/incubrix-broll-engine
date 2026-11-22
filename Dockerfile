FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1 PIP_NO_CACHE_DIR=1 HF_HOME=/models/hf PIPER_DATA_DIR=/models/voices
RUN apt-get update && apt-get install -y --no-install-recommends ffmpeg && rm -rf /var/lib/apt/lists/*
WORKDIR /app
RUN pip install torch torchvision --index-url https://download.pytorch.org/whl/cpu
COPY requirements-docker.txt .
RUN pip install -r requirements-docker.txt
RUN python -m spacy download en_core_web_sm
RUN python -m piper.download_voices en_US-ljspeech-medium --data-dir /models/voices
RUN python -c "from faster_whisper import WhisperModel; WhisperModel('base', device='cpu', compute_type='int8')"
RUN python -c "import open_clip; open_clip.create_model_and_transforms('ViT-B-32', pretrained='laion2b_s34b_b79k')"
RUN pip install "moto[s3]"
COPY app ./app
COPY scripts ./scripts
COPY tests ./tests
COPY pytest.ini .
EXPOSE 8000
CMD ["uvicorn", "app.main:create", "--factory", "--host", "0.0.0.0", "--port", "8000"]
