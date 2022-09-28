FROM python:3.9.14-slim-bullseye AS builder
WORKDIR /app
RUN apt update \
 && apt install -y curl \
 && rm -rf /var/lib/apt/lists/*
RUN curl -sSLf https://github.com/bitnami-labs/sealed-secrets/releases/download/v0.18.2/kubeseal-0.18.2-linux-amd64.tar.gz | tar xzf - \
 && chmod a+x kubeseal
ADD . /app
RUN pip install --target=/app -r requirements.txt

# A distroless container image with Python and some basics like SSL certificates
# https://github.com/GoogleContainerTools/distroless
FROM gcr.io/distroless/python3-debian10@sha256:b0041237ec3b3009275c1e0698fd7339940f2736d3359874da71bebd0878ed0a
COPY --from=builder /app /app
WORKDIR /app
ENV PYTHONPATH /app
CMD ["/app/main.py"]
