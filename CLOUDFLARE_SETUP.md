# Cloudflare Origin SSL Setup

## Steps:

### 1. Generate Cloudflare Origin Certificate
1. Go to Cloudflare Dashboard → SSL/TLS → Origin Server
2. Click "Create Certificate"
3. Select "Generate private key and CSR with Cloudflare"
4. Choose validity (15 years recommended)
5. Click "Create"
6. Copy both certificate and private key

### 2. Save Certificates on VPS
```bash
# Create SSL directory
mkdir -p ssl

# Save origin certificate
nano ssl/cert.pem
# Paste the certificate content
chmod 700 ssl/
chmod 600 ssl/key.pem
chmod 644 ssl/cert.pem



# Save private key
nano ssl/key.pem
# Paste the private key content

# Set permissions
chmod 600 ssl/key.pem
chmod 644 ssl/cert.pem
```

### 3. Update nginx.conf
Edit `nginx.conf` and replace `your-domain.com` with your actual domain.

### 4. Cloudflare Settings
- **DNS**: Add A record pointing to your VPS IP (Proxied/Orange cloud)
- **SSL/TLS Mode**: Set to "Full" (not Full Strict)
- **Always Use HTTPS**: Enable

### 5. Deploy
```bash
docker-compose up -d --build
```

### 6. Test
Visit `https://your-domain.com/health` - should return `{"status":"healthy"}`

## Troubleshooting
- Check nginx logs: `docker-compose logs nginx`
- Check app logs: `docker-compose logs vpn_bot`
- Verify SSL files exist: `ls -la ssl/`
