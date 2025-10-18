# 🤖 LeaX AI - Complete Deployment Guide

## 🎯 What is LeaX?

**LeaX is an all-in-one AI business automation platform that:**
- ✅ Answers phone calls & texts 24/7
- ✅ Closes sales automatically
- ✅ Bids on jobs at lightning speed
- ✅ Tracks government funding revenue
- ✅ Manages HR and customer service
- ✅ Works on ANY device (Windows, Mac, Linux, iOS, Android)

**Setup Time:** 5 minutes  
**Technical Knowledge Required:** None  
**Monthly Cost:** Starting at $29

---

## 📦 Installation Methods

### Method 1: Download Desktop App (Recommended for Most Users)

**Windows:**
```
1. Download: https://download.leax.ai/windows/LeaX-Setup.exe
2. Double-click to install
3. Follow setup wizard
4. Done! 🎉
```

**macOS:**
```
1. Download: https://download.leax.ai/mac/LeaX-Installer.dmg
2. Drag to Applications folder
3. Open LeaX
4. Done! 🎉
```

**Linux:**
```bash
curl -fsSL https://install.leax.ai/linux | bash
```

### Method 2: One-Line Web Install (Super Fast)

**Windows (PowerShell):**
```powershell
iwr -useb https://install.leax.ai/windows | iex
```

**Mac/Linux:**
```bash
curl -fsSL https://install.leax.ai | bash
```

### Method 3: Cloud Deployment (For Businesses)

**Railway (Easiest):**
```bash
# 1. Fork this repo on GitHub
# 2. Go to railway.app
# 3. Click "New Project" → "Deploy from GitHub"
# 4. Select your fork
# 5. Add environment variables (see below)
# 6. Deploy! 🚀
```

**Heroku:**
```bash
git clone https://github.com/leax-ai/app
cd app
heroku create your-app-name
git push heroku main
```

**Docker:**
```bash
docker-compose up -d
```

---

## ⚙️ Environment Variables

Create a `.env` file or set these in your hosting platform:

```env
# Required
OPENAI_API_KEY=sk-your-key-here
FLASK_SECRET=your-random-secret-key

# For Phone/SMS (Optional - can setup later)
TWILIO_ACCOUNT_SID=your-twilio-sid
TWILIO_AUTH_TOKEN=your-twilio-token

# For Email Notifications (Optional)
SMTP_USERNAME=your-email@domain.com
EMAIL_PASSWORD=your-email-password
SMTP_SERVER=smtp.office365.com
SMTP_PORT=587

# For PayPal (Optional)
PAYPAL_CLIENT_ID=your-paypal-client-id
PAYPAL_CLIENT_SECRET=your-paypal-secret
```

---

## 🚀 Quick Start (5 Minutes)

### Step 1: Install & Launch (2 minutes)
- Download and run installer for your platform
- App opens automatically after install

### Step 2: Create Account (1 minute)
- Enter your business name and email
- Choose a password
- Click "Start Free Trial"

### Step 3: Customize Your AI (1 minute)
- Paste your website URL (we'll scan it automatically)
- OR type a few sentences about your business
- Give your AI agent a name (e.g., "Sarah")

### Step 4: Test It! (1 minute)
- Click "Test Agent"
- Chat with your AI
- See how it responds to customer questions

### Step 5: Connect Your Phone (Optional)
**Option A - Get New Number (Instant):**
- Click "Phone Setup" → "Get New Number"
- We provision a number automatically (30 seconds)
- Done! Your AI is now answering calls

**Option B - Forward Existing Number:**
- Click "Phone Setup" → "Forward Existing"
- Follow the simple forwarding instructions
- Test by calling your number

**Option C - Setup Later:**
- Skip for now, come back anytime

---

## 🎯 Advanced Features Setup

### Auto-Bidding for Job Platforms

**What it does:**
- Monitors Upwork, Thumbtack, HomeAdvisor, etc.
- Automatically bids on matching jobs
- Responds to client messages
- Lightning-fast (bids in seconds)

**Setup:**
1. Click "Auto-Bidding" in dashboard
2. Select platforms you use
3. Login to each platform (one-time)
4. Configure bidding strategy
5. Enable auto-bidding
6. Done! 🎯

**Platforms Supported:**
- ✅ Upwork
- ✅ Thumbtack
- ✅ HomeAdvisor
- ✅ Angi (Angie's List)
- ✅ Bark
- ✅ TaskRabbit
- ✅ Fiverr
- ✅ Custom platforms (via API)

### Government Funding Tracker

**What it does:**
- Automatically tracks accessibility services
- Generates FCC compliance reports
- Calculates monthly revenue from:
  - IP CTS (captions): $1.40/minute
  - STS (speech assist): $1.75/minute
  - Lifeline: $9.25/month per customer
  - ACP: $30/month per customer

**Setup:**
1. Go to "Funding Dashboard"
2. Enable accessibility features
3. That's it! Revenue tracked automatically

---

## 📱 Mobile App Setup

### iOS (iPhone/iPad)
```
1. Download from App Store (coming soon)
2. Or use web app: https://app.leax.ai
3. Add to home screen for full-screen experience
```

### Android
```
1. Download from Google Play (coming soon)
2. Or use web app: https://app.leax.ai
3. Add to home screen
```

---

## 🔧 Configuration Files

### Desktop App Location

**Windows:**
```
C:\Users\YourName\AppData\Local\LeaX\
```

**macOS:**
```
/Users/YourName/Library/Application Support/LeaX/
```

**Linux:**
```
~/.local/share/leax/
```

### Data Storage

All your data is stored locally in:
```
~/.leax/
├── config.json          # App configuration
├── leax_users.db        # User database
├── customer_memories/   # AI memory files
├── logs/               # Activity logs
├── backups/            # Auto backups
└── browser_profiles/   # Auto-bidding logins
```

---

## 🔐 Security & Privacy

- ✅ All data stored locally on YOUR device
- ✅ Encrypted database
- ✅ No data sent to our servers (except API calls)
- ✅ You own all your data
- ✅ GDPR compliant
- ✅ HIPAA ready (for healthcare businesses)

---

## 🆘 Troubleshooting

### App Won't Start
```bash
# Check if port 8080 is available
netstat -an | grep 8080

# Kill any process using port 8080
# Windows:
taskkill /F /IM python.exe

# Mac/Linux:
killall python3
```

### Phone Not Working
```
1. Check Twilio credentials in Settings
2. Verify webhook URL is correct
3. Test with a manual SMS first
4. Check firewall isn't blocking connections
```

### Auto-Bidding Not Working
```
1. Make sure you're logged into platforms
2. Check browser profiles weren't cleared
3. Verify platform didn't change their layout
4. Check logs: ~/.leax/logs/bidding.log
```

### Database Issues
```bash
# Backup current database
cp ~/.leax/leax_users.db ~/.leax/leax_users.db.backup

# Reset database (WARNING: loses data)
rm ~/.leax/leax_users.db
# Restart app - it will create new database
```

---

## 📊 Usage & Limits

### Free Trial
- ✅ 100 test messages
- ✅ All features unlocked
- ✅ No credit card required
- ⏰ 7 days

### Basic Plan ($29/month)
- ✅ 1,000 messages/month
- ✅ 1 phone number
- ✅ Basic lead tracking
- ✅ Email support

### Standard Plan ($59/month)
- ✅ 5,000 messages/month
- ✅ 3 phone numbers
- ✅ Advanced analytics
- ✅ Auto-bidding (3 platforms)
- ✅ Priority support

### Enterprise Plan ($149/month)
- ✅ Unlimited messages
- ✅ Unlimited phone numbers
- ✅ White-label option
- ✅ Auto-bidding (all platforms)
- ✅ API access
- ✅ Dedicated support

---

## 🛠️ For Developers

### Run from Source

```bash
# Clone repository
git clone https://github.com/leax-ai/app
cd app

# Install dependencies
pip install -r requirements.txt

# Set environment variables
export OPENAI_API_KEY=your-key
export FLASK_SECRET=your-secret

# Run
python main.py
```

### API Documentation

**Base URL:** `http://localhost:8080/api`

**Endpoints:**

```
POST /api/test-chat
Body: {"message": "Hello"}
Response: {"reply": "Hi! How can I help?"}

GET /api/leads
Response: [{lead_id, phone, score, ...}, ...]

POST /api/enable-accessibility
Body: {"feature": "captions", "enabled": true}
Response: {"success": true}

GET /api/funding/monthly
Response: {"total_monthly": 1234.56, ...}
```

### Custom Integrations

```python
from leax import LeaXClient

# Initialize
client = LeaXClient(api_key='your-api-key')

# Send message
response = client.chat('Customer message here')

# Get leads
leads = client.get_leads(score_min=70)

# Track funding
earnings = client.get_funding_earnings(month=10, year=2025)
```

---

## 🌐 Cloud Hosting Options

### Recommended: Railway
- ✅ Easiest setup
- ✅ Auto-scaling
- ✅ Free tier available
- ✅ One-click deploy

### Alternative: Heroku
- ✅ Well-documented
- ✅ Large ecosystem
- ⚠️  More expensive

### Self-Hosted: Docker
```bash
docker run -d \
  -p 8080:8080 \
  -e OPENAI_API_KEY=your-key \
  -v leax_data:/data \
  leax/app:latest
```

---

## 📞 Support

### Community Support (Free)
- 💬 Discord: https://discord.gg/leax
- 📧 Email: support@leax.ai
- 📚 Docs: https://docs.leax.ai

### Priority Support (Paid Plans)
- 🎯 Direct Slack channel
- 📞 Phone support
- ⚡ < 1 hour response time

### Enterprise Support
- 👨‍💼 Dedicated account manager
- 🔧 Custom development
- 📊 Training sessions
- 🚀 White-glove onboarding

---

## 🎓 Training Resources

### Video Tutorials
- 📹 [5-Minute Setup Guide](https://youtube.com/leax/setup)
- 📹 [Auto-Bidding Tutorial](https://youtube.com/leax/bidding)
- 📹 [Advanced Features](https://youtube.com/leax/advanced)

### Written Guides
- 📝 [Customizing Your AI Agent](https://docs.leax.ai/customize)
- 📝 [Government Funding Guide](https://docs.leax.ai/funding)
- 📝 [Auto-Bidding Best Practices](https://docs.leax.ai/bidding)

---

## 🚀 Roadmap

### Coming Soon
- [ ] iOS/Android native apps
- [ ] CRM integrations (Salesforce, HubSpot)
- [ ] Multi-language support
- [ ] Voice cloning (sound like you!)
- [ ] Advanced analytics dashboard

### Under Consideration
- [ ] Team collaboration features
- [ ] Appointment scheduling integration
- [ ] Payment processing
- [ ] Custom AI training
- [ ] API marketplace

---

## 📄 License

LeaX is proprietary software.  
© 2025 American Power LLC. All rights reserved.

---

## 🤝 Contributing

We welcome contributions! See [CONTRIBUTING.md](CONTRIBUTING.md) for guidelines.

---

## ⭐ Success Stories

> "LeaX helped me close 3x more jobs while I sleep. Game changer!"  
> — Mike, Plumbing Business Owner

> "The auto-bidding feature got me 15 new clients in the first week!"  
> — Sarah, Freelance Designer

> "Government funding tracker pays for itself. I'm making an extra $2,000/month!"  
> — John, Accessibility Services Provider

---

**Ready to get started? [Download LeaX Now](https://download.leax.ai) 🚀**
