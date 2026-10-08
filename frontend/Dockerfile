FROM node:22-alpine AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY . .
ARG APP_VERSION=dev
ENV VITE_APP_VERSION=$APP_VERSION
RUN npm run build

# Unprivileged nginx: runs as a non-root user and listens on 8080. The official entrypoint fills
# ${API_UPSTREAM} into the template at start.
FROM nginxinc/nginx-unprivileged:1.27-alpine
LABEL org.opencontainers.image.source="https://github.com/slin86/kontor"
ENV API_UPSTREAM=api:8000
COPY nginx.conf.template /etc/nginx/templates/default.conf.template
COPY --from=build /app/dist /usr/share/nginx/html
EXPOSE 8080
