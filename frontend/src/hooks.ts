import { useQuery, useMutation, useQueryClient } from "@tanstack/react-query";
import {
  fetchHoldings,
  fetchOrders,
  fetchProtectionStatus,
  fetchSchedulerStatus,
  fetchEtfs,
  runAmoProtection,
  cancelAllOrders,
  buyEtf,
} from "./api";
import type {
  HoldingsResponse,
  OrdersResponse,
  ProtectionStatus,
  SchedulerStatus,
  ETFResponse,
  BuyOrderRequest,
  ApiResponse,
} from "./types";

// Portfolio queries
export function useHoldings() {
  return useQuery<HoldingsResponse>({
    queryKey: ["holdings"],
    queryFn: fetchHoldings,
    staleTime: 30000,
  });
}

export function useOrders() {
  return useQuery<OrdersResponse>({
    queryKey: ["orders"],
    queryFn: fetchOrders,
    staleTime: 30000,
  });
}

export function useProtectionStatus() {
  return useQuery<ProtectionStatus>({
    queryKey: ["protectionStatus"],
    queryFn: fetchProtectionStatus,
    staleTime: 30000,
  });
}

export function useSchedulerStatus() {
  return useQuery<SchedulerStatus>({
    queryKey: ["schedulerStatus"],
    queryFn: fetchSchedulerStatus,
    staleTime: 60000,
  });
}

// ETF queries
export function useEtfs() {
  return useQuery<ETFResponse>({
    queryKey: ["etfs"],
    queryFn: fetchEtfs,
    staleTime: 60000,
  });
}

// Mutations
export function useRunAmoProtection() {
  const queryClient = useQueryClient();

  return useMutation<ApiResponse, Error>({
    mutationFn: runAmoProtection,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["protectionStatus"] });
    },
  });
}

export function useCancelAllOrders() {
  const queryClient = useQueryClient();

  return useMutation<ApiResponse, Error>({
    mutationFn: cancelAllOrders,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["protectionStatus"] });
    },
  });
}

export function useBuyEtf() {
  const queryClient = useQueryClient();

  return useMutation<ApiResponse, Error, BuyOrderRequest>({
    mutationFn: buyEtf,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["holdings"] });
    },
  });
}
