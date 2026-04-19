#!/usr/bin/env python3
"""Railway deployment helper script.

This script helps configure and deploy the bot to Railway.
"""
import os
import sys
import subprocess

def check_git():
    """Check if git is configured."""
    try:
        subprocess.run(['git', '--version'], check=True, capture_output=True)
        return True
    except:
        return False

def main():
    print("🚂 Railway Deployment Helper")
    print("=" * 50)
    
    # Check git
    if not check_git():
        print("❌ Git not found. Install git first:")
        print("   macOS: brew install git")
        print("   Ubuntu: sudo apt install git")
        sys.exit(1)
    
    # Check if in git repo
    if not os.path.exists('.git'):
        print("❌ Not a git repository. Run from project root.")
        sys.exit(1)
    
    print("\n📋 Pre-deployment checklist:")
    print()
    
    # Check .env.example exists
    if not os.path.exists('.env.example'):
        print("❌ .env.example not found")
        sys.exit(1)
    
    # Read current .env if exists
    env_vars = {}
    if os.path.exists('.env'):
        with open('.env', 'r') as f:
            for line in f:
                if '=' in line and not line.startswith('#'):
                    key, val = line.strip().split('=', 1)
                    env_vars[key] = val
    
    print("1️⃣  Checking environment variables...")
    
    required = [
        'POKER_BOT_TOKEN',
        'POKER_ADMIN_IDS',
        'KASPI_PHONE_NUMBER'
    ]
    
    missing = []
    for var in required:
        if not env_vars.get(var) or env_vars.get(var) == 'your_value_here':
            missing.append(var)
    
    if missing:
        print(f"   ⚠️  Missing required variables: {', '.join(missing)}")
        print("   Edit .env file and add them")
    else:
        print("   ✅ All required variables set")
    
    # Add webhook config
    print("\n2️⃣  Webhook configuration...")
    
    if env_vars.get('USE_WEBHOOK') == 'true':
        webhook_url = env_vars.get('WEBHOOK_URL', '')
        if webhook_url and 'railway' in webhook_url:
            print(f"   ✅ Webhook URL: {webhook_url}")
        else:
            print("   ⚠️  You'll need to update WEBHOOK_URL after first deploy")
    else:
        print("   ℹ️  Polling mode (for local testing)")
    
    # Check if railway CLI installed
    print("\n3️⃣  Checking Railway CLI...")
    try:
        result = subprocess.run(['railway', '--version'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✅ Railway CLI installed: {result.stdout.strip()}")
        else:
            raise Exception("Not installed")
    except:
        print("   ❌ Railway CLI not installed")
        print("\n   Install with:")
        print("   npm install -g @railway/cli")
        print("   Or: brew install railway")
        print("\n   Then login: railway login")
        sys.exit(1)
    
    # Check if logged in
    try:
        result = subprocess.run(['railway', 'whoami'], capture_output=True, text=True)
        if result.returncode == 0:
            print(f"   ✅ Logged in as: {result.stdout.strip()}")
        else:
            raise Exception("Not logged in")
    except:
        print("   ❌ Not logged in to Railway")
        print("   Run: railway login")
        sys.exit(1)
    
    print("\n" + "=" * 50)
    print("\n🚀 Ready to deploy!")
    print("\nNext steps:")
    print("1. Ensure all code is committed:")
    print("   git add -A && git commit -m 'Ready for deploy'")
    print("2. Link to Railway project:")
    print("   railway link")
    print("3. Deploy:")
    print("   railway up")
    print("\nOr use GitHub integration (recommended):")
    print("1. Push to GitHub: git push origin main")
    print("2. Go to https://railway.app")
    print("3. Click '+ New' → 'Deploy from GitHub repo'")
    print("4. Select your repository")
    print("5. Add environment variables in Railway dashboard")
    print()

if __name__ == '__main__':
    main()
