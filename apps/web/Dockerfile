FROM node:20-alpine AS deps
WORKDIR /app/apps/web
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM deps AS builder
ARG NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
ENV NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}
COPY apps/web ./
RUN npm run build \
    && npm prune --omit=dev

FROM node:20-alpine AS runner
WORKDIR /app/apps/web

ARG NEXT_PUBLIC_API_BASE_URL=http://127.0.0.1:8000
ENV NODE_ENV=production \
    HOSTNAME=0.0.0.0 \
    PORT=3000 \
    NEXT_PUBLIC_API_BASE_URL=${NEXT_PUBLIC_API_BASE_URL}

RUN apk add --no-cache curl

COPY --from=builder /app/apps/web ./

EXPOSE 3000

HEALTHCHECK --interval=15s --timeout=5s --retries=6 CMD curl -fsS http://127.0.0.1:3000/ >/dev/null || exit 1

CMD ["npm", "run", "start", "--", "--hostname", "0.0.0.0", "--port", "3000"]
