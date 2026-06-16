import { createContext, useCallback, useContext, useState } from 'react';
import { AlertTriangle } from 'lucide-react';

const ConfirmContext = createContext(null);

export const useConfirm = () => {
  const ctx = useContext(ConfirmContext);
  if (!ctx) throw new Error('useConfirm must be used within ConfirmProvider');
  return ctx;
};

export const ConfirmProvider = ({ children }) => {
  const [state, setState] = useState(null);

  const confirm = useCallback((opts = {}) => {
    return new Promise((resolve) => {
      setState({
        title: opts.title || '¿Confirmar acción?',
        description: opts.description || '',
        confirmText: opts.confirmText || 'Confirmar',
        cancelText: opts.cancelText || 'Cancelar',
        danger: opts.danger !== false, // default to destructive styling
        resolve,
      });
    });
  }, []);

  const close = (result) => {
    if (state?.resolve) state.resolve(result);
    setState(null);
  };

  return (
    <ConfirmContext.Provider value={confirm}>
      {children}
      {state && (
        <div className="fixed inset-0 z-[60] flex items-center justify-center p-4 bg-ink-900/50"
          onClick={() => close(false)} data-testid="confirm-dialog">
          <div className="bg-white rounded-2xl p-6 w-full max-w-md shadow-xl" onClick={(e) => e.stopPropagation()}>
            <div className={`w-12 h-12 rounded-full flex items-center justify-center ${state.danger ? 'bg-red-100 text-red-600' : 'bg-brand-50 text-brand-500'}`}>
              <AlertTriangle className="w-6 h-6" />
            </div>
            <h3 className="font-display text-xl font-semibold text-ink-900 mt-4" data-testid="confirm-title">{state.title}</h3>
            {state.description && <p className="text-sm text-ink-500 mt-1" data-testid="confirm-description">{state.description}</p>}
            <div className="flex justify-end gap-2 mt-6">
              <button className="btn-ghost" onClick={() => close(false)} data-testid="confirm-cancel">{state.cancelText}</button>
              <button className={`btn-primary ${state.danger ? '!bg-red-600 hover:!bg-red-700' : ''}`}
                onClick={() => close(true)} data-testid="confirm-accept">{state.confirmText}</button>
            </div>
          </div>
        </div>
      )}
    </ConfirmContext.Provider>
  );
};
