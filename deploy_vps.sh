#!/bin/bash
# PokerHubs VPS Deployment Script
# Run this on your VPS after cloning the repo

set -e

echo "🚀 Starting PokerHubs deployment..."

# Update system
echo "📦 Updating system packages..."
apt-get update
apt-get install -y python3 python3-pip python3-venv git curl

# Create app directory
mkdir -p /opt/pokerhubs
cd /opt/pokerhubs

# Clone repo (if not already cloned)
if [ ! -d ".git" ]; then
    echo "📥 Cloning repository..."
    git clone https://github.com/MansurCyberDev/PokerHubs.git .
fi

# Create virtual environment
echo "🐍 Creating Python virtual environment..."
python3 -m venv venv
source venv/bin/activate

# Install dependencies
echo "📦 Installing dependencies..."
pip install --upgrade pip
pip install -r requirements.txt

# Create environment file
echo "⚙️  Setting up environment..."
if [ ! -f ".env" ]; then
    cat > .env << 'EOF'
POKER_BOT_TOKEN=8633427504:AAGASNDFuoBo174hfI2HXoa72lVx228tIBs
POKER_ADMIN_IDS=5491969475
POKER_SUPPORT_USERNAME=golovorezsm
KASPI_CARD=4400430233136370
POKER_MIN_PLAYERS=2
POKER_MAX_PLAYERS=9
POKER_STARTING_STACK=1000
POKER_SMALL_BLIND=10
POKER_BIG_BLIND=20
POKER_REGISTRATION_TIME=120
POKER_TURN_TIME=60
EOF
    echo "⚠️  Created .env file - verify the bot token is correct!"
fi

# Create systemd service
echo "🔧 Creating systemd service..."
cat > /etc/systemd/system/pokerhubs.service << 'EOF'
[Unit]
Description=PokerHubs Telegram Bot
After=network.target

[Service]
Type=simple
User=root
WorkingDirectory=/opt/pokerhubs
Environment=PYTHONUNBUFFERED=1
ExecStart=/opt/pokerhubs/venv/bin/python main.py
Restart=always
RestartSec=10

[Install]
WantedBy=multi-user.target
EOF

# Reload systemd and start service
systemctl daemon-reload
systemctl enable pokerhubs
systemctl start pokerhubs

echo "✅ Deployment complete!"
echo ""
echo "📊 Service status:"
systemctl status pokerhubs --no-pager

echo ""
echo "📝 Useful commands:"
echo "  View logs: journalctl -u pokerhubs -f"
echo "  Restart: systemctl restart pokerhubs"
echo "  Stop: systemctl stop pokerhubs"
