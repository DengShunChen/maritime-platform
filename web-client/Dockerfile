FROM node:22-alpine AS build-stage

WORKDIR /app
ARG VITE_MAPTILER_API_KEY=ci-placeholder
ARG BUILD_VERSION=dev
ARG BUILD_SHA=unknown
ARG BUILD_DATE=unknown
ENV VITE_MAPTILER_API_KEY=$VITE_MAPTILER_API_KEY

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

# Production stage
FROM nginx:stable-alpine AS production-stage
ARG BUILD_VERSION=dev
ARG BUILD_SHA=unknown
ARG BUILD_DATE=unknown
LABEL org.opencontainers.image.title="Maritime Platform Web Client" \
      org.opencontainers.image.version="${BUILD_VERSION}" \
      org.opencontainers.image.revision="${BUILD_SHA}" \
      org.opencontainers.image.created="${BUILD_DATE}"

COPY --from=build-stage /app/dist /usr/share/nginx/html
COPY nginx.conf.template /etc/nginx/templates/default.conf.template

# Add healthcheck for nginx
HEALTHCHECK --interval=30s --timeout=10s --retries=3 \
  CMD wget -q -O /dev/null http://localhost/ || exit 1

EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
