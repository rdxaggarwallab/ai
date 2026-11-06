# Development (docker-compose.yml): Vite dev server with hot reload.
FROM node:22-slim AS dev
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["npm", "run", "dev", "--", "--port", "3000", "--host"]

# Production (docker-compose.prod.yml): build once, serve static files with nginx.
FROM dev AS build
RUN npm run build

FROM nginx:1.27-alpine AS prod
COPY deploy/nginx.conf /etc/nginx/conf.d/default.conf
COPY --from=build /app/dist /usr/share/nginx/html
