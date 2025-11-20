#!/bin/bash

echo "🚀 Deploying VPN Bot..."

# Stop existing container
docker-compose down

# Build and start
docker-compose up -d --build

# Show logs
docker-compose logs -f
