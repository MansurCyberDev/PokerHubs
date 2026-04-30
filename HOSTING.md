# PokerHubs Hosting Guide

## VPS Deployment (Recommended)

Your VPS: `185.212.129.2` | Domain: `pokerhubs.com`

### Quick Setup

1. **SSH into your VPS:**
```bash
ssh root@185.212.129.2
# Password: Mansur282348@228
```

2. **Run deployment script:**
```bash
cd /opt
git clone https://github.com/MansurCyberDev/PokerHubs.git
cd PokerHubs
chmod +x deploy_vps.sh
./deploy_vps.sh
```

3. **Verify bot is running:**
```bash
systemctl status pokerhubs
journalctl -u pokerhubs -f
```

### Manual Setup

If the script doesn't work:

```bash
# 1. Install dependencies
apt-get update
apt-get install -y python3 python3-pip python3-venv git

# 2. Setup app
cd /opt
git clone https://github.com/MansurCyberDev/PokerHubs.git
cd PokerHubs
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt

# 3. Create .env file
cat > .env << 'EOF'
POKER_BOT_TOKEN=your_token_here
POKER_ADMIN_IDS=5491969475
POKER_SUPPORT_USERNAME=golovorezsm
KASPI_CARD=4400430233136370
EOF

# 4. Run bot
python main.py
```

### Service Management

```bash
# Check status
systemctl status pokerhubs

# View logs
journalctl -u pokerhubs -f

# Restart bot
systemctl restart pokerhubs

# Stop bot
systemctl stop pokerhubs
```

### Files

- Bot code: `/opt/PokerHubs/`
- Database: `/opt/PokerHubs/poker_stats.db`
- Logs: `journalctl -u pokerhubs`

## Docker Deployment

```bash
docker build -t pokerhubs .
docker run -d \
  -e POKER_BOT_TOKEN=your_token \
  -v $(pwd)/poker_stats.db:/app/poker_stats.db \
  --name pokerhubs \
  --restart always \
  pokerhubs
```

## Environment Variables

| Variable | Required | Default |
|----------|----------|---------|
| `POKER_BOT_TOKEN` | ✅ | - |
| `POKER_ADMIN_IDS` | ❌ | `5491969475` |
| `POKER_SUPPORT_USERNAME` | ❌ | `golovorezsm` |
| `KASPI_CARD` | ❌ | `4400430233136370` |
| `POKER_MIN_PLAYERS` | ❌ | `2` |
| `POKER_MAX_PLAYERS` | ❌ | `9` |
| `POKER_STARTING_STACK` | ❌ | `1000` |

## Support

Contact: @golovorezsm
