FROM python:3.12-slim
RUN pip install --no-cache-dir huggingface_hub==0.26.2
RUN useradd -m -u 1000 user
USER user
WORKDIR /home/user/app
COPY --chown=user app.py .
ENV PYTHONUNBUFFERED=1 DATA_DIR=/tmp/nyay PORT=7860
EXPOSE 7860
CMD ["python", "app.py"]
