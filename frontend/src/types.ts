// API Response Types
export interface Holding {
  symbol: string;
  trading_symbol?: string;
  quantity: number;
  average_cost: number;
  ltp: number;
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
  protected_holdings: number;
  unprotected_holdings: number;
  pending_orders: number;
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
