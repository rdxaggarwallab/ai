FROM node:22-slim
WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
CMD ["npx", "vite", "--port", "3000", "--host"]
