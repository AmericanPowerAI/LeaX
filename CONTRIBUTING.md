# Contributing to LeaX

## How to Contribute

1. Fork the repository
2. Create your feature branch (`git checkout -b feature/AmazingFeature`)
3. Commit your changes (`git commit -m 'Add some AmazingFeature'`)
4. Push to the branch (`git push origin feature/AmazingFeature`)
5. Open a Pull Request

## Development Setup

```bash
git clone https://github.com/yourusername/leax
cd leax
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env
python main.py
```

## Code Style

- Follow PEP 8
- Add docstrings to all functions
- Write tests for new features
- Keep functions small and focused

## Testing

```bash
python -m pytest tests/
```

## Need Help?

- Join our Discord: https://discord.gg/leax
- Email: dev@leax.ai
