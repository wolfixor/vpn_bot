#!/bin/bash
# MongoDB Backup Script

BACKUP_DIR="./backups"
DATE=$(date +%Y%m%d_%H%M%S)
BACKUP_NAME="vpn_bot_backup_$DATE"

mkdir -p $BACKUP_DIR

echo "🔄 Starting MongoDB backup..."

# Extract MongoDB connection details from .env
source .env

# Create backup
mongodump --uri="$MONGODB_URL" --out="$BACKUP_DIR/$BACKUP_NAME"

echo "✅ Backup completed: $BACKUP_DIR/$BACKUP_NAME"

# Keep only last 7 backups
cd $BACKUP_DIR
ls -t | tail -n +8 | xargs rm -rf

echo "🧹 Old backups cleaned up"
