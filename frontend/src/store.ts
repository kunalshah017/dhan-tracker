import { create } from "zustand";
import { persist } from "zustand/middleware";

interface AuthState {
  password: string;
  isAuthenticated: boolean;
  setPassword: (password: string) => void;
  login: (password: string) => Promise<boolean>;
  logout: () => void;
  getPassword: () => string;
}

export const useAuthStore = create<AuthState>()(
  persist(
    (set, get) => ({
      password: "",
      isAuthenticated: false,

      setPassword: (password: string) => set({ password }),

      login: async (password: string) => {
        set({ password });
        try {
          const response = await fetch("/health", {
            headers: { "X-Password": password },
          });
          if (!response.ok) throw new Error("Unauthorized");
          set({ isAuthenticated: true });
          return true;
        } catch (err) {
          set({ password: "", isAuthenticated: false });
          throw err;
        }
      },

      logout: () => set({ password: "", isAuthenticated: false }),

      getPassword: () => get().password,
    }),
    {
      name: "dhan-auth",
      partialize: (state) => ({ password: state.password }),
    },
  ),
);
