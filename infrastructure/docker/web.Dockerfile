FROM node:22-alpine AS deps
WORKDIR /app
COPY apps/web/package.json apps/web/package-lock.json ./
RUN npm ci

FROM node:22-alpine AS build
WORKDIR /app
COPY --from=deps /app/node_modules ./node_modules
COPY apps/web/ .
# Next.js evaluates rewrites at build time, so the API origin is a build argument.
ARG ONEFINANCE_API_URL=http://api:8000
ENV NEXT_TELEMETRY_DISABLED=1 ONEFINANCE_API_URL=$ONEFINANCE_API_URL
RUN npm run build

FROM node:22-alpine
WORKDIR /app
ENV NODE_ENV=production NEXT_TELEMETRY_DISABLED=1
COPY --from=build /app ./
RUN adduser -D -u 10001 app && chown -R app /app
USER app
EXPOSE 3000
CMD ["npx", "next", "start", "-p", "3000"]
