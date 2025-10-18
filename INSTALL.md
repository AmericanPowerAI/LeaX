# LeaX AI - Installation Guide

## Quick Install (5 minutes)

### Step 1: Download
Visit: https://download.leax.ai
Choose your platform: Windows | macOS | Linux

### Step 2: Install
- **Windows**: Run LeaX-Setup.exe
- **macOS**: Drag to Applications
- **Linux**: `curl -fsSL https://install.leax.ai | bash`

### Step 3: Configure
1. Open LeaX
2. Enter your OpenAI API key
3. Create your account
4. Done!

## Cloud Deployment

### Railway (Recommended)
```bash
# 1. Fork repo on GitHub
# 2. Go to railway.app
# 3. New Project → Deploy from GitHub
# 4. Add environment variables from .env.example
# 5. Deploy!
```

### Docker
```bash
docker-compose up -d
```

### Manual Install
```bash
git clone https://github.com/leax-ai/app
cd app
pip install -r requirements.txt
cp .env.example .env
# Edit .env with your keys
python main.py
```

Visit: http://localhost:8080
