# Build from the repo root:  docker build -f bridge/Dockerfile -t ptouch-bridge .
FROM python:3.13-slim
RUN apt-get update && apt-get install -y --no-install-recommends libusb-1.0-0 \
    && rm -rf /var/lib/apt/lists/* \
    && pip install --no-cache-dir pillow pyusb
WORKDIR /app
COPY custom_components/brother_ptouch/ptouch /app/ptouch_core/ptouch
COPY bridge/ptouch_bridge.py /app/
EXPOSE 8765
ENTRYPOINT ["python", "/app/ptouch_bridge.py"]
