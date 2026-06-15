FROM node:20-alpine

WORKDIR /usr/src/app

# Install dependencies first (better layer caching)
COPY package.json yarn.lock* ./
RUN yarn install --production --frozen-lockfile || yarn install --production

COPY server.js ./

# Persistent auth sessions live here (mount a volume)
RUN mkdir -p /data/auth
ENV AUTH_DIR=/data/auth
ENV PORT=3001

EXPOSE 3001
CMD ["node", "server.js"]
