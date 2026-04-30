FROM node:20-alpine AS deps
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM deps AS builder
COPY apps/web ./
RUN npm run build \
    && npm prune --omit=dev

FROM node:20-alpine AS runner
WORKDIR /app/apps/web

ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    API_BASE_URL=http://api:8000

RUN apk add --no-cache curl

COPY --from=builder /app/apps/web ./

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --retries=6 CMD curl -fsS http://127.0.0.1:3000/ >/dev/null || exit 1

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
