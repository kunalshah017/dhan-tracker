# Dhan Tracker

A portfolio tracking and protection tool for Dhan trading accounts. Automatically places **Super Orders** with stop-loss to protect your holdings against market falls.

## Features

- 📊 **Portfolio Tracking**: View all your holdings and positions
- 🛡️ **Automatic Protection**: Place protective super orders with stop-loss on all holdings
- 📉 **Stop Loss Orders**: Configurable stop-loss percentage (default: 5%)
- 🎯 **Target Orders**: Optional target price for profit booking
- 📈 **Trailing Stop Loss**: Support for trailing stop loss
- ⏰ **Daily Scheduling**: Run protection automatically at market open

## Installation

```bash
# Clone the repository
cd dhan-tracker

# Install dependencies
pip install -e .

# Or using uv
uv pip install -e .
```

## Configuration

1. First, initialize the configuration:

```bash
python main.py init
```

2. Edit the config file at `~/.dhan-tracker/config.env`:

```env
# Get your access token from https://web.dhan.co
# My Profile -> Access DhanHQ APIs

DHAN_ACCESS_TOKEN=your_access_token_here
DHAN_CLIENT_ID=your_client_id_here

# Stop loss percentage (default: 5%)
DHAN_STOP_LOSS_PERCENT=5.0
```

### Getting Access Token

1. Login to [web.dhan.co](https://web.dhan.co)
2. Click on **My Profile**
3. Navigate to **Access DhanHQ APIs**
4. Generate **Access Token** (valid for 24 hours)

## Usage

### View Portfolio

```bash
# Show all holdings
python main.py holdings

# Show open positions
python main.py positions

# Show protection status
python main.py status
```

### Protect Portfolio

```bash
# Place protective orders with default 5% stop loss
python main.py protect

# Use custom stop loss percentage
python main.py protect --sl 3

# With target price (20% above avg cost)
python main.py protect --sl 5 --target 20

# With trailing stop loss
python main.py protect --sl 5 --trail 10

# Force replace existing orders
python main.py protect --force
```

### Manage Super Orders

```bash
# View all super orders
python main.py orders

# Cancel all protection orders
python main.py cancel

# Cancel specific order
python main.py cancel --order-id 112111182198
```

## How Protection Works

1. **Fetch Holdings**: Gets all your current holdings from Dhan
2. **Calculate Stop Loss**: For each holding, calculates stop loss price (e.g., 5% below avg cost)
3. **Place Super Order**: Places a SELL super order with:
   - Entry at current price
   - Stop Loss leg for downside protection
   - Target leg for profit booking (optional)
4. **DDPI Compatible**: Uses super orders which work with DDPI authorization

### Example

If you hold HDFC Bank at avg cost ₹1,500:

- Stop Loss (5%): ₹1,425
- Target (20%): ₹1,800

The super order will:

- Sell if price drops to ₹1,425 (protecting against further fall)
- Sell if price rises to ₹1,800 (booking profit)

## Daily Protection Schedule

For automated daily protection, you can:

### Using Task Scheduler (Windows)

Create a scheduled task to run at 9:15 AM:

```bash
python main.py protect
```

### Using Cron (Linux/Mac)

Add to crontab:

```cron
15 9 * * 1-5 cd /path/to/dhan-tracker && python main.py protect
```

## API Endpoints Used

| Endpoint                      | Method | Purpose                  |
| ----------------------------- | ------ | ------------------------ |
| `/v2/holdings`                | GET    | Fetch portfolio holdings |
| `/v2/positions`               | GET    | Fetch open positions     |
| `/v2/super/orders`            | GET    | List super orders        |
| `/v2/super/orders`            | POST   | Place super order        |
| `/v2/super/orders/{id}/{leg}` | DELETE | Cancel super order       |

## Project Structure

```
dhan-tracker/
├── main.py                    # CLI entry point
├── pyproject.toml             # Project configuration
├── README.md                  # This file
└── src/
    └── dhan_tracker/
        ├── __init__.py
        ├── client.py          # Dhan API client
        ├── config.py          # Configuration management
        ├── models.py          # Data models
        ├── protection.py      # Protection strategies
        └── scheduler.py       # Daily scheduling
```

## Important Notes

⚠️ **Super Order Requirements**:

- Super orders require **Static IP whitelisting** on Dhan
- Contact Dhan support to whitelist your IP

⚠️ **Token Validity**:

- Access tokens are valid for **24 hours only**
- Refresh daily or use the API to renew

⚠️ **Market Hours**:

- Orders are only valid during market hours (9:15 AM - 3:30 PM IST)
- Run protection at market open for best results

## License

MIT License

## Disclaimer

This tool is for educational purposes. Trading involves risk. Always verify orders before market opens. The developers are not responsible for any financial losses.
