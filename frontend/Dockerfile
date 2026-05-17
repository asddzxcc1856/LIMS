# Two-stage build for production:
#  1) Vite builds the SPA → /app/dist
#  2) Caddy 2 serves the SPA + reverse-proxies /api/* to the Django backend,
#     and automatically obtains + renews a Let's Encrypt cert for HTTPS.
#
# Caddy reads ./Caddyfile from this directory at build time (copied to
# /etc/caddy/Caddyfile inside the image).
FROM node:20-alpine AS build

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .
RUN npm run build

FROM nginx:alpine

COPY --from=build /app/dist /usr/share/nginx/html

EXPOSE 8080

CMD ["sh", "-c", "sed -i 's/listen       80;/listen 8080;/g' /etc/nginx/conf.d/default.conf && nginx -g 'daemon off;'"]
