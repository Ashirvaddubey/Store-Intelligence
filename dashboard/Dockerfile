# ── Store Intelligence Dashboard ────────────────────────────────────
# Node 20 proxy + WebSocket server for the live dashboard UI
# ────────────────────────────────────────────────────────────────────
FROM node:20-alpine

# Install wget for health probe
RUN apk add --no-cache wget

WORKDIR /app

ENV NODE_ENV=production

# Install dependencies first (layer cache)
COPY dashboard/package.json ./package.json
RUN npm install --production --silent

# Copy dashboard source
COPY dashboard/ .

EXPOSE 3000

# Built-in health probe
HEALTHCHECK --interval=15s --timeout=5s --start-period=10s --retries=3 \
  CMD wget -qO- http://localhost:3000/health || exit 1

CMD ["node", "server.js"]
