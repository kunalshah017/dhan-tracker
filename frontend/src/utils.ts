import type { ETF } from "./types";

// Format currency in INR
export function formatCurrency(value: number): string {
  return "₹" + value.toLocaleString("en-IN", { maximumFractionDigits: 2 });
}

// Format volume
export function formatVolume(value: number): string {
  if (value >= 10000000) return (value / 10000000).toFixed(2) + " Cr";
  if (value >= 100000) return (value / 100000).toFixed(2) + " L";
  if (value >= 1000) return (value / 1000).toFixed(1) + " K";
  return value.toString();
}

// ETF category type
export type ETFCategory = "gold" | "silver" | "bank" | "it" | "nifty" | "other";

// Categorize ETF by symbol/underlying
export function getCategory(etf: ETF): ETFCategory {
  const symbol = etf.symbol.toUpperCase();
  const underlying = etf.underlying.toUpperCase();

  if (symbol.includes("GOLD") || underlying.includes("GOLD")) return "gold";
  if (
    symbol.includes("SILVER") ||
    symbol.includes("SILV") ||
    underlying.includes("SILVER")
  )
    return "silver";
  if (symbol.includes("BANK") || underlying.includes("BANK")) return "bank";
  if (symbol.includes("IT") || underlying.includes("IT ")) return "it";
  if (symbol.includes("NIFTY") || underlying.includes("NIFTY")) return "nifty";
  return "other";
}
