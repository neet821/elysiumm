FROM node:22.18.0-bookworm-slim

WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev
COPY server.cjs ./

USER node
CMD ["node", "server.cjs"]
