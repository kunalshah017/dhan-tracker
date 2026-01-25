import { create } from 'zustand';
import { persist } from 'zustand/middleware';

export const useAuthStore = create(
    persist(
        (set, get) => ({
            password: '',
            isAuthenticated: false,

            setPassword: (password) => set({ password }),

            login: async (password) => {
                set({ password });
                try {
                    const response = await fetch('/health', {
                        headers: { 'X-Password': password }
                    });
                    if (!response.ok) throw new Error('Unauthorized');
                    set({ isAuthenticated: true });
                    return true;
                } catch (err) {
                    set({ password: '', isAuthenticated: false });
                    throw err;
                }
            },

            logout: () => set({ password: '', isAuthenticated: false }),

            getPassword: () => get().password,
        }),
        {
            name: 'dhan-auth',
            partialize: (state) => ({ password: state.password }),
            onRehydrateStorage: () => (state) => {
                // Check if stored password is still valid on rehydrate
                if (state?.password) {
                    fetch('/health', {
                        headers: { 'X-Password': state.password }
                    })
                        .then(res => {
                            if (res.ok) {
                                state.isAuthenticated = true;
                            } else {
                                state.password = '';
                                state.isAuthenticated = false;
                            }
                        })
                        .catch(() => {
                            state.password = '';
                            state.isAuthenticated = false;
                        });
                }
            }
        }
    )
);
