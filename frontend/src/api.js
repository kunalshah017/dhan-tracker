import { useAuthStore } from "./AuthContext";

// Base API function
export async function api(endpoint, options = {}) {
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

// API functions
export const fetchHoldings = () => api("/api/holdings");
export const fetchOrders = () => api("/api/orders/regular");
export const fetchProtectionStatus = () => api("/api/protection/status");
export const fetchSchedulerStatus = () => api("/api/scheduler/status");
export const fetchEtfs = () => api("/api/etf");

export const runAmoProtection = () =>
  api("/api/protection/run-amo", { method: "POST" });
export const cancelAllOrders = () =>
  api("/api/protection/cancel", { method: "POST" });

export const buyEtf = (data) =>
  api("/api/etf/buy", {
    method: "POST",
    body: JSON.stringify(data),
  });
