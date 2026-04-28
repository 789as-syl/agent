FROM node:22-alpine AS build

WORKDIR /app

COPY front/client/package.json front/client/package-lock.json ./front/client/
COPY front/shared ./front/shared

WORKDIR /app/front/client
RUN npm ci

WORKDIR /app
COPY front/client ./front/client
RUN npm --prefix front/client run build

FROM nginx:1.27-alpine

COPY deploy/nginx/frontend-spa.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/front/client/dist /usr/share/nginx/html

