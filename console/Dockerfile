FROM node:22.17.0-alpine3.21@sha256:0d722d537f07d5e962b82733cd641cfa1fb868eab8c597ebfc87b8fa0436daa9 AS build
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci
COPY tsconfig.json tsconfig.app.json tsconfig.node.json vite.config.ts index.html ./
COPY public ./public
COPY src ./src
RUN npm run build

FROM node:22.17.0-alpine3.21@sha256:0d722d537f07d5e962b82733cd641cfa1fb868eab8c597ebfc87b8fa0436daa9 AS runtime
ENV NODE_ENV=production \
    PORT=8080 \
    STATIC_DIR=/app/dist
WORKDIR /app
COPY package.json package-lock.json ./
RUN npm ci --omit=dev --ignore-scripts && npm cache clean --force
COPY bff ./bff
COPY --from=build /app/dist ./dist
USER node
EXPOSE 8080
HEALTHCHECK --interval=20s --timeout=3s --start-period=10s --retries=3 \
  CMD node -e "fetch('http://127.0.0.1:8080/healthz').then(r=>{if(!r.ok)process.exit(1)}).catch(()=>process.exit(1))"
CMD ["node", "bff/server.mjs"]
