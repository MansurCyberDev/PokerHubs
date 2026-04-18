# 🚀 Deployment Guide

## Quick Start

```bash
# 1. Clone repository
git clone https://github.com/MansurCyberDev/PokerHubs.git
cd PokerHubs

# 2. Create virtual environment
python3 -m venv venv
source venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Setup environment
cp .env.example .env
# Edit .env with your values

# 5. Create required directories
mkdir -p logs backups

# 6. Run bot
python3 main.py
```

## Production Server Setup

### 1. Server Requirements
- Ubuntu 20.04+ / Debian 11+
- Python 3.9+
- 2GB RAM minimum
- 10GB disk space

### 2. Install System Dependencies

```bash
# Update system
sudo apt update && sudo apt upgrade -y

# Install Python and dependencies
sudo apt install -y python3-pip python3-venv git ffmpeg sqlite3

# Install Node.js (for PM2 process manager)
curl -fsSL https://deb.nodesource.com/setup_18.x | sudo -E bash -
sudo apt install -y nodejs

# Install PM2
sudo npm install -g pm2
```

### 3. Create Service User

```bash
# Create dedicated user
sudo useradd -m -s /bin/bash pokerbot
sudo usermod -aG sudo pokerbot

# Switch to user
su - pokerbot
```

### 4. Deploy Application

```bash
# Clone repository
git clone https://github.com/MansurCyberDev/PokerHubs.git ~/pokerbot
cd ~/pokerbot

# Create virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install --upgrade pip
pip install -r requirements.txt

# Create environment file
cp .env.example .env
nano .env  # Edit with your values

# Create directories
mkdir -p logs backups
```

### 5. PM2 Configuration

Create `ecosystem.config.js`:

```javascript
module.exports = {
  apps: [{
    name: 'poker-bot',
    script: './main.py',
    interpreter: './venv/bin/python3',
    instances: 1,
    autorestart: true,
    watch: false,
    max_memory_restart: '1G',
    env: {
      NODE_ENV: 'production'
    },
    log_date_format: 'YYYY-MM-DD HH:mm:ss',
    error_file: './logs/pm2-error.log',
    out_file: './logs/pm2-out.log',
    log_file: './logs/pm2-combined.log',
    time: true
  }]
};
```

Start with PM2:

```bash
# Start bot
pm2 start ecosystem.config.js

# Save PM2 config
pm2 save

# Setup startup script
sudo env PATH=$PATH:/usr/bin pm2 startup systemd -u pokerbot --hp /home/pokerbot

# Check status
pm2 status
pm2 logs poker-bot
```

### 6. Nginx Reverse Proxy (Optional)

For webhook setup (recommended for production):

```bash
sudo apt install nginx

# Create config
sudo nano /etc/nginx/sites-available/poker-bot
```

```nginx
server {
    listen 80;
    server_name your-domain.com;
    
    location /webhook {
        proxy_pass http://127.0.0.1:8080;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection 'upgrade';
        proxy_set_header Host $host;
        proxy_cache_bypass $http_upgrade;
    }
}
```

```bash
sudo ln -s /etc/nginx/sites-available/poker-bot /etc/nginx/sites-enabled/
sudo nginx -t
sudo systemctl restart nginx
```

### 7. SSL Certificate (Let's Encrypt)

```bash
sudo apt install certbot python3-certbot-nginx
sudo certbot --nginx -d your-domain.com
sudo systemctl enable certbot.timer
```

### 8. Backup Automation

Add cron job for additional backups:

```bash
# Edit crontab
crontab -e

# Add line for daily backup at 3 AM
0 3 * * * cd ~/pokerbot && ./venv/bin/python3 -c "from backup import DatabaseBackup; b = DatabaseBackup(); b.create_backup('daily'); b.cleanup_old_backups()"

# Add line for weekly full backup ( Sundays at 4 AM)
0 4 * * 0 cd ~/pokerbot && tar -czf ~/backups/pokerbot-full-$(date +\%Y\%m\%d).tar.gz ~/pokerbot/logs ~/pokerbot/*.db ~/pokerbot/backups
```

### 9. Monitoring & Alerts

Create monitoring script `monitor.sh`:

```bash
#!/bin/bash
# Save as ~/pokerbot/monitor.sh

BOT_STATUS=$(pm2 status poker-bot | grep "poker-bot" | grep -c "online")
DISK_USAGE=$(df / | tail -1 | awk '{print $5}' | sed 's/%//')

if [ "$BOT_STATUS" -eq 0 ]; then
    # Send alert via Telegram
    curl -s -X POST "https://api.telegram.org/bot$YOUR_BOT_TOKEN/sendMessage" \
        -d "chat_id=$ADMIN_CHAT_ID" \
        -d "text=🚨 Poker Bot is DOWN!"
fi

if [ "$DISK_USAGE" -gt 80 ]; then
    curl -s -X POST "https://api.telegram.org/bot$YOUR_BOT_TOKEN/sendMessage" \
        -d "chat_id=$ADMIN_CHAT_ID" \
        -d "text=⚠️ Disk usage is ${DISK_USAGE}%!"
fi
```

```bash
chmod +x ~/pokerbot/monitor.sh

# Add to crontab (check every 5 minutes)
crontab -e
*/5 * * * * ~/pokerbot/monitor.sh
```

### 10. Health Check Command

For admins to check bot health:

```
/admin health
```

Or check via PM2:

```bash
pm2 status
pm2 logs poker-bot --lines 100
```

## Update Deployment

```bash
# Pull latest changes
cd ~/pokerbot
git pull

# Restart bot
pm2 restart poker-bot

# Check logs
pm2 logs poker-bot
```

## Troubleshooting

### Bot Not Starting

```bash
# Check Python syntax
python3 -m py_compile main.py

# Check logs
tail -f logs/bot.log

# Test without PM2
./venv/bin/python3 main.py
```

### Database Issues

```bash
# Check database integrity
sqlite3 poker_stats.db "PRAGMA integrity_check;"

# Restore from backup
./venv/bin/python3 -c "from backup import DatabaseBackup; b = DatabaseBackup(); b.restore_backup()"
```

### Memory Issues

```bash
# Restart bot
pm2 restart poker-bot

# Check memory usage
pm2 monit
```

## Environment Variables Reference

| Variable | Required | Default | Description |
|----------|----------|---------|-------------|
| `POKER_BOT_TOKEN` | Yes | - | Telegram bot token |
| `POKER_ADMIN_IDS` | Yes | - | Comma-separated admin IDs |
| `KASPI_PHONE_NUMBER` | Yes | +77012345678 | Payment phone number |
| `POKER_SUPPORT_USERNAME` | No | - | Support contact |
| `POKER_MIN_PLAYERS` | No | 2 | Minimum players |
| `POKER_MAX_PLAYERS` | No | 9 | Maximum players |
| `POKER_STARTING_STACK` | No | 1000 | Starting chips |
| `POKER_SMALL_BLIND` | No | 10 | Small blind |
| `POKER_BIG_BLIND` | No | 20 | Big blind |
| `POKER_REGISTRATION_TIME` | No | 120 | Registration timeout (sec) |
| `POKER_TURN_TIME` | No | 60 | Turn timeout (sec) |

## Security Checklist

- [ ] Bot token is kept secret
- [ ] .env file is in .gitignore
- [ ] Admin IDs are correctly set
- [ ] Kaspi phone number is verified
- [ ] Server firewall is enabled (ufw)
- [ ] Automatic backups are configured
- [ ] Monitoring alerts are active
- [ ] SSL certificate is installed
- [ ] Logs are rotated (10MB × 5 files)
