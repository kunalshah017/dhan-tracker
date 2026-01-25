import { create } from 'zustand';

const useToastStore = create((set) => ({
    toasts: [],
    addToast: (message, type = 'success') => {
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
        success: (message) => addToast(message, 'success'),
        error: (message) => addToast(message, 'error')
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
