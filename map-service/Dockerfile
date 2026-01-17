FROM node:22-slim

# Install dependencies for canvas/sharp if needed (Debian slim includes some, but explicit is better)
# sharp typically needs python3, make, g++
RUN apt-get update && apt-get install -y \
    python3 \
    make \
    g++ \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install dependencies
COPY package.json package-lock.json ./
RUN npm ci --omit=dev

# Copy application code
COPY . .

# Create cache directory
RUN mkdir -p /app/cache && chown -R node:node /app/cache

# Run as non-root user
USER node

# Expose port (Cloud Run sets PORT env var, defaults to 8080 usually)
ENV PORT 3001
EXPOSE 3001

CMD ["node", "server.js"]
