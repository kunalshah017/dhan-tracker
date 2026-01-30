// API Response Types
export interface Holding {
  symbol: string;
  quantity: number;
  avg_cost: number;
  ltp: number;
  invested: number;
  current_value: number;
  pnl: number;
  pnl_percent: number;
}

export interface Order {
  orderId: string;
  tradingSymbol: string;
  quantity: number;
  price: number;
  transactionType: string;
  orderStatus: string;
}

export interface ProtectionStatus {
  total_holdings: number;
  protected_count: number;
  unprotected_count: number;
  total_value: number;
  protected_value: number;
  protection_percent: number;
  last_run?: string;
  last_result?: Record<string, unknown>;
}

export interface SchedulerJob {
  id: string;
  next_run_time: string | null;
  trigger: string;
}

export interface SchedulerStatus {
  jobs: SchedulerJob[];
}

export interface HoldingsResponse {
  holdings: Holding[];
  total_invested: number;
  total_current: number;
  total_pnl: number;
  total_pnl_percent: number;
}

export interface OrdersResponse {
  orders: Order[];
}

export interface ETF {
  symbol: string;
  underlying: string;
  ltp: number;
  nav: number;
  discount_premium: number;
  pchange: number;
  volume: number;
  turnover: number;
}

export interface ETFResponse {
  etfs: ETF[];
}

export interface BuyOrderRequest {
  symbol: string;
  quantity: number;
  order_type: "MARKET" | "LIMIT";
  price?: number;
}

export interface ApiResponse {
  message: string;
  status?: string;
}

export interface TokenStatus {
  database_enabled: boolean;
  token_source: string;
  last_refresh: string | null;
  last_refresh_result: {
    status: string;
    timestamp: string;
    message?: string;
    error?: string;
  } | null;
  token_info?: {
    stored_at: string | null;
    expires_at: string | null;
    client_id: string;
    token_length: number;
  };
}
