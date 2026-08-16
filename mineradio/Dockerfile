FROM node:20-bookworm-slim

RUN apt-get update \
    && apt-get install -y --no-install-recommends chromium \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY . .

ENV HOST=0.0.0.0
ENV PORT=3000
ENV MINERADIO_CHROMIUM_PATH=/usr/bin/chromium
EXPOSE 3000
CMD ["node", "server.js"]
