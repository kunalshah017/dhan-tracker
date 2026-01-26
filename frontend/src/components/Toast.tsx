import { create } from 'zustand';

interface Toast {
    id: number;
    message: string;
    type: 'success' | 'error';
}

interface ToastState {
    toasts: Toast[];
    addToast: (message: string, type?: 'success' | 'error') => void;
}

const useToastStore = create<ToastState>((set) => ({
    toasts: [],
    addToast: (message: string, type: 'success' | 'error' = 'success') => {
        const id = Date.now();
        set((state) => ({
            toasts: [...state.toasts, { id, message, type }]
        }));
        setTimeout(() => {
            set((state) => ({
                toasts: state.toasts.filter(t => t.id !== id)
            }));
        }, 3000);
    }
}));

export function useToast() {
    const addToast = useToastStore((state) => state.addToast);
    return {
        success: (message: string) => addToast(message, 'success'),
        error: (message: string) => addToast(message, 'error')
    };
}

export function ToastContainer() {
    const toasts = useToastStore((state) => state.toasts);

    return (
        <>
            {toasts.map((toast) => (
                <div key={toast.id} className={`toast ${toast.type}`}>
                    {toast.message}
                </div>
            ))}
        </>
    );
}
