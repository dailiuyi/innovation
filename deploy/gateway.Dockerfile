FROM node:22.18.0-alpine3.22 AS build
WORKDIR /build
COPY frontend/package.json frontend/package-lock.json ./
RUN npm ci
COPY frontend/ ./
RUN npm run build:prod

FROM nginx:1.28.0-alpine3.21
COPY --from=build /build/dist/ /usr/share/nginx/html/
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
EXPOSE 8080
