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

// Portfolio queries
export function useHoldings() {
  return useQuery({
    queryKey: ["holdings"],
    queryFn: fetchHoldings,
    staleTime: 30000, // 30 seconds
  });
}

export function useOrders() {
  return useQuery({
    queryKey: ["orders"],
    queryFn: fetchOrders,
    staleTime: 30000,
  });
}

export function useProtectionStatus() {
  return useQuery({
    queryKey: ["protectionStatus"],
    queryFn: fetchProtectionStatus,
    staleTime: 30000,
  });
}

export function useSchedulerStatus() {
  return useQuery({
    queryKey: ["schedulerStatus"],
    queryFn: fetchSchedulerStatus,
    staleTime: 60000, // 1 minute
  });
}

// ETF queries
export function useEtfs() {
  return useQuery({
    queryKey: ["etfs"],
    queryFn: fetchEtfs,
    staleTime: 60000,
  });
}

// Mutations
export function useRunAmoProtection() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: runAmoProtection,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["protectionStatus"] });
    },
  });
}

export function useCancelAllOrders() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: cancelAllOrders,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["orders"] });
      queryClient.invalidateQueries({ queryKey: ["protectionStatus"] });
    },
  });
}

export function useBuyEtf() {
  const queryClient = useQueryClient();

  return useMutation({
    mutationFn: buyEtf,
    onSuccess: () => {
      queryClient.invalidateQueries({ queryKey: ["holdings"] });
    },
  });
}
