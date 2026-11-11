# Development image. A slimmer multi-stage build comes with the deploy stage.
FROM node:24-slim

WORKDIR /app
ENV NEXT_TELEMETRY_DISABLED=1

# Install dependencies first so this layer is cached while only source code changes.
COPY package.json package-lock.json ./
RUN npm ci

COPY . .
RUN npm run build

EXPOSE 3000

CMD ["npm", "run", "start"]
