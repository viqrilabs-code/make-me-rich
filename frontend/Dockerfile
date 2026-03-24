FROM node:20-alpine AS deps
WORKDIR /app
COPY frontend/package.json ./package.json
RUN npm install

FROM node:20-alpine AS builder
WORKDIR /app
ARG API_SERVER_ORIGIN=http://localhost:8000
ARG NEXT_PUBLIC_API_BASE_URL=
ENV API_SERVER_ORIGIN=$API_SERVER_ORIGIN
ENV NEXT_PUBLIC_API_BASE_URL=$NEXT_PUBLIC_API_BASE_URL
COPY --from=deps /app/node_modules ./node_modules
COPY frontend ./
RUN npm run build

FROM node:20-alpine AS runner
WORKDIR /app
ENV NODE_ENV=production
COPY --from=builder /app/.next/standalone ./
COPY --from=builder /app/.next/static ./.next/static
COPY --from=builder /app/public ./public
EXPOSE 3000
CMD ["node", "server.js"]
