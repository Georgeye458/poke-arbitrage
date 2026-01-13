# PokeArbitrage Scanner

A web application that identifies undervalued PSA 10 Pokemon cards on eBay by comparing "Buy It Now" listings against broader market value trends.

## Features

- 🔍 **Automated Scanning**: Monitors 22 high-value PSA 10 Pokemon cards every 30 minutes
- 💰 **Smart Filtering**: Focuses on cards under $3,000 AUD for better liquidity
- 📊 **Market Benchmarks**: Uses eBay Merchandising API for reliable market pricing
- 🎯 **Arbitrage Detection**: Flags listings priced 15%+ below market value
- 🌐 **Web Dashboard**: View opportunities through a clean HTML interface

## Tech Stack

- **Backend**: Python, FastAPI
- **Task Queue**: Celery + Redis
- **Database**: PostgreSQL
- **APIs**: eBay Browse API + Merchandising API
- **Hosting**: Heroku

## Setup

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/georgeye458/poke-arbitrage.git
cd poke-arbitrage
```

2. Create virtual environment:
```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

3. Install dependencies:
```bash
pip install -r requirements.txt
```

4. Copy environment template:
```bash
cp .env.example .env
```

5. Configure your eBay API credentials in `.env`

6. Run database migrations:
```bash
alembic upgrade head
```

7. Start the services:
```bash
# Terminal 1: FastAPI
uvicorn app.main:app --reload

# Terminal 2: Celery Worker
celery -A app.tasks.celery_app worker --loglevel=info

# Terminal 3: Celery Beat (Scheduler)
celery -A app.tasks.celery_app beat --loglevel=info
```

### Heroku Deployment

```bash
heroku create poke-arbitrage
heroku addons:create heroku-postgresql:essential-0
heroku addons:create heroku-redis:mini
heroku config:set EBAY_APP_ID=your_app_id
heroku config:set EBAY_CERT_ID=your_cert_id
# ... set other env vars
git push heroku main
heroku ps:scale web=1 worker=1 beat=1
```

## API Endpoints

- `GET /` - Health check
- `GET /opportunities` - View arbitrage opportunities (HTML)
- `GET /api/opportunities` - Get opportunities as JSON

## Architecture

```
┌─────────────────┐     ┌──────────────────┐
│  Celery Beat    │────▶│   Redis Queue    │
│  (Scheduler)    │     └────────┬─────────┘
└─────────────────┘              │
                                 ▼
┌─────────────────┐     ┌──────────────────┐
│  eBay APIs      │◀────│  Celery Worker   │
│  Browse +       │     │  (3 Tasks)       │
│  Merchandising  │     └────────┬─────────┘
└─────────────────┘              │
                                 ▼
┌─────────────────┐     ┌──────────────────┐
│  FastAPI        │◀────│   PostgreSQL     │
│  Web App        │     │   Database       │
└─────────────────┘     └──────────────────┘
```

## License

MIT
