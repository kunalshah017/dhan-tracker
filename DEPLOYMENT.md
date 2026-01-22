# Dhan Portfolio Tracker - Azure Deployment Guide

## Overview

This is a FastAPI server that tracks your Dhan portfolio and automatically places protective DDPI super orders with stop-loss daily at market open.

## Features

- 📊 View portfolio holdings with real-time LTP from NSE
- 🛡️ Automatic daily protection orders at 9:20 AM IST
- 🔄 Manual trigger for protection via API
- 📈 View all super orders
- ⏰ Scheduler status and management

## API Endpoints

| Endpoint                 | Method | Description                            |
| ------------------------ | ------ | -------------------------------------- |
| `/`                      | GET    | Health check with scheduler status     |
| `/health`                | GET    | Simple health check for load balancers |
| `/api/holdings`          | GET    | Get portfolio with current LTP         |
| `/api/orders`            | GET    | Get all super orders                   |
| `/api/protection/status` | GET    | Get protection status                  |
| `/api/protection/run`    | POST   | Manually run protection                |
| `/api/protection/cancel` | POST   | Cancel all protection orders           |
| `/api/scheduler/status`  | GET    | View scheduled jobs                    |
| `/api/scheduler/trigger` | POST   | Manually trigger scheduled job         |

## Local Development

### 1. Install dependencies

```bash
uv sync
# or
pip install -r requirements.txt
```

### 2. Set environment variables

Create a `.env` file:

```env
DHAN_ACCESS_TOKEN=your_access_token_here
DHAN_CLIENT_ID=your_client_id_here
DHAN_STOP_LOSS_PERCENT=5.0
```

### 3. Run the server

```bash
# Using uvicorn directly
uvicorn server:app --reload --host 0.0.0.0 --port 8000

# Or using Python
python server.py
```

### 4. Access the API

- Swagger UI: http://localhost:8000/docs
- ReDoc: http://localhost:8000/redoc
- Health: http://localhost:8000/

## Azure App Service Deployment

### Option 1: Deploy via Azure CLI

```bash
# Login to Azure
az login

# Create resource group (if needed)
az group create --name dhan-tracker-rg --location centralindia

# Create App Service Plan (B1 is minimum for Always On)
az appservice plan create \
  --name dhan-tracker-plan \
  --resource-group dhan-tracker-rg \
  --sku B1 \
  --is-linux

# Create Web App
az webapp create \
  --name dhan-tracker-app \
  --resource-group dhan-tracker-rg \
  --plan dhan-tracker-plan \
  --runtime "PYTHON:3.11"

# Configure startup command
az webapp config set \
  --name dhan-tracker-app \
  --resource-group dhan-tracker-rg \
  --startup-file "gunicorn --bind=0.0.0.0 --timeout 600 --worker-class uvicorn.workers.UvicornWorker server:app"

# Set environment variables
az webapp config appsettings set \
  --name dhan-tracker-app \
  --resource-group dhan-tracker-rg \
  --settings \
    DHAN_ACCESS_TOKEN="your_token" \
    DHAN_CLIENT_ID="your_client_id" \
    DHAN_STOP_LOSS_PERCENT="5.0"

# Enable Always On (required for scheduler to run)
az webapp config set \
  --name dhan-tracker-app \
  --resource-group dhan-tracker-rg \
  --always-on true

# Deploy code
az webapp up \
  --name dhan-tracker-app \
  --resource-group dhan-tracker-rg \
  --runtime "PYTHON:3.11"
```

### Option 2: Deploy via GitHub Actions

1. Create `.github/workflows/azure-deploy.yml` (provided below)
2. Set up deployment credentials in GitHub Secrets
3. Push to main branch

### Option 3: Deploy via VS Code

1. Install Azure App Service extension
2. Right-click on the project folder
3. Select "Deploy to Web App"
4. Follow the prompts

## Important Azure Settings

### 1. Always On (Required!)

The scheduler needs the app to be always running:

```bash
az webapp config set --name dhan-tracker-app --resource-group dhan-tracker-rg --always-on true
```

### 2. Environment Variables

Set these in Azure Portal > App Service > Configuration > Application settings:

| Name                     | Description                         |
| ------------------------ | ----------------------------------- |
| `DHAN_ACCESS_TOKEN`      | Your Dhan API access token          |
| `DHAN_CLIENT_ID`         | Your Dhan client ID                 |
| `DHAN_STOP_LOSS_PERCENT` | Stop loss percentage (default: 5.0) |

### 3. Timezone

The scheduler uses IST (Asia/Kolkata) for market hours.

## Scheduler

The server runs three scheduled jobs:

1. **Token Refresh**: Every 23 hours (proactive, before token expires)
   - Refreshes the Dhan access token before it expires
   - Critical for keeping the server running without manual intervention
   
2. **AMO Protection**: Daily at 8:30 AM IST (before market opens at 9:15 AM)
   - Places After Market Orders (SL orders active from market open)
   
3. **Daily Protection**: Daily at 9:20 AM IST (after market opens)
   - Places Super Orders with stop-loss and target prices

You can:

- Check status: `GET /api/scheduler/status`
- Manually trigger: `POST /api/scheduler/trigger`

## Monitoring

- View logs in Azure Portal > App Service > Log stream
- Check health at `https://your-app.azurewebsites.net/health`

## Cost Estimation

- **B1 Plan**: ~$13/month (minimum for Always On)
- **Free Tier**: Won't work (no Always On, scheduler won't run)

## Troubleshooting

### Scheduler not running

- Ensure "Always On" is enabled
- Check if app is in sleep mode (Free/Shared tiers)

### 401 errors from Dhan API

- **Token expired**: If you see 401 errors, the access token has likely expired
- **Automatic refresh**: The server refreshes tokens every 23 hours automatically
- **Server downtime**: If the server was down for >24 hours, the token expired and cannot be auto-refreshed
- **Solution**: Generate a new token from [web.dhan.co](https://web.dhan.co) and update `DHAN_ACCESS_TOKEN` in Azure environment variables
- **Important**: Token refresh ONLY works if called BEFORE the token expires - it cannot revive an expired token

### NSE API errors

- NSE may block requests during heavy traffic
- Try again after a few minutes
