FROM node:22-alpine AS build

WORKDIR /app

COPY front/admin/package.json front/admin/package-lock.json ./front/admin/
COPY front/shared ./front/shared

WORKDIR /app/front/admin
RUN npm ci

WORKDIR /app
COPY front/admin ./front/admin
RUN npm --prefix front/admin run build

FROM nginx:1.27-alpine

COPY deploy/nginx/frontend-spa.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/front/admin/dist /usr/share/nginx/html

