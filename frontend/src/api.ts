import { useAuthStore } from "./store";
import type {
  HoldingsResponse,
  OrdersResponse,
  ProtectionStatus,
  SchedulerStatus,
  ETFResponse,
  BuyOrderRequest,
  ApiResponse,
  TokenStatus,
} from "./types";

interface FetchOptions extends RequestInit {
  headers?: Record<string, string>;
}

// Base API function
export async function api<T>(
  endpoint: string,
  options: FetchOptions = {},
): Promise<T> {
  const password = useAuthStore.getState().password;

  const response = await fetch(endpoint, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      "X-Password": password,
      ...options.headers,
    },
  });

  if (response.status === 401) {
    useAuthStore.getState().logout();
    throw new Error("Unauthorized");
  }

  if (!response.ok) {
    const error = await response.json().catch(() => ({ detail: "API Error" }));
    throw new Error(error.detail || "API Error");
  }

  return response.json();
}

// API functions with proper typing
export const fetchHoldings = (): Promise<HoldingsResponse> =>
  api<HoldingsResponse>("/api/holdings");
export const fetchOrders = (): Promise<OrdersResponse> =>
  api<OrdersResponse>("/api/orders/regular");
export const fetchProtectionStatus = (): Promise<ProtectionStatus> =>
  api<ProtectionStatus>("/api/protection/status");
export const fetchSchedulerStatus = (): Promise<SchedulerStatus> =>
  api<SchedulerStatus>("/api/scheduler/status");
export const fetchEtfs = (): Promise<ETFResponse> =>
  api<ETFResponse>("/api/etf");

export const runAmoProtection = (): Promise<ApiResponse> =>
  api<ApiResponse>("/api/protection/run", { method: "POST" });

export const runSuperOrderProtection = (): Promise<ApiResponse> =>
  api<ApiResponse>("/api/protection/run", { method: "POST" });

export const cancelAllOrders = (): Promise<ApiResponse> =>
  api<ApiResponse>("/api/protection/cancel", { method: "POST" });

export const buyEtf = (data: BuyOrderRequest): Promise<ApiResponse> =>
  api<ApiResponse>("/api/etf/buy", {
    method: "POST",
    body: JSON.stringify(data),
  });

// Token management APIs
export const fetchTokenStatus = (): Promise<TokenStatus> =>
  api<TokenStatus>("/api/token/status");

export const refreshToken = (): Promise<ApiResponse> =>
  api<ApiResponse>("/api/token/refresh", { method: "POST" });

export const updateApiKey = (accessToken: string): Promise<ApiResponse> =>
  api<ApiResponse>("/api/token/update", {
    method: "POST",
    body: JSON.stringify({ access_token: accessToken }),
  });
