FROM node:20-slim

# git + toolchain de compilación: algunas dependencias de Baileys ejecutan
# scripts que requieren git, y los módulos nativos (node-gyp) necesitan
# python3/make/g++ durante el `yarn install`.
RUN apt-get update \
    && apt-get install -y --no-install-recommends git python3 make g++ ca-certificates \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /usr/src/app

# Install dependencies first (better layer caching).
# yarn.lock* (con comodín) hace que el COPY no falle si el lockfile no está
# presente en el contexto. Intentamos frozen-lockfile (reproducible) y si el
# lockfile faltara, hacemos un install normal: el pin EXACTO de baileys en
# package.json garantiza la versión segura igual.
COPY package.json yarn.lock* ./
RUN yarn install --production --frozen-lockfile || yarn install --production

COPY server.js ./

# Persistent auth sessions live here (mount a volume)
RUN mkdir -p /data/auth
ENV AUTH_DIR=/data/auth
ENV PORT=3001

EXPOSE 3001
CMD ["node", "server.js"]
