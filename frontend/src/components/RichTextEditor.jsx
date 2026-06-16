import { useRef, useEffect } from 'react';
import { Bold, Italic, Underline, List, ListOrdered } from 'lucide-react';

/**
 * Lightweight contentEditable rich-text editor (bold/italic/underline + lists).
 * Outputs sanitized-on-backend HTML. Used for the company cancellation policy.
 */
export function RichTextEditor({ value, onChange, placeholder = '', testid = 'rich-editor' }) {
  const ref = useRef(null);

  // Set initial HTML only once (avoid caret jumps while typing).
  useEffect(() => {
    if (ref.current && (value || '') !== ref.current.innerHTML) {
      ref.current.innerHTML = value || '';
    }
    // eslint-disable-next-line
  }, []);

  const emit = () => onChange(ref.current ? ref.current.innerHTML : '');

  const exec = (cmd) => {
    document.execCommand(cmd, false, null);
    ref.current?.focus();
    emit();
  };

  const Btn = ({ cmd, icon: Icon, label }) => (
    <button type="button" title={label}
      onMouseDown={(e) => { e.preventDefault(); exec(cmd); }}
      className="p-2 rounded-lg hover:bg-brand-50 text-ink-600 transition-colors"
      data-testid={`${testid}-${cmd}`}>
      <Icon className="w-4 h-4" />
    </button>
  );

  return (
    <div className="rounded-xl border border-ink-200 overflow-hidden bg-white" data-testid={testid}>
      <div className="flex items-center gap-1 border-b border-ink-100 bg-cream px-2 py-1.5">
        <Btn cmd="bold" icon={Bold} label="Negrita" />
        <Btn cmd="italic" icon={Italic} label="Cursiva" />
        <Btn cmd="underline" icon={Underline} label="Subrayado" />
        <span className="w-px h-5 bg-ink-200 mx-1" />
        <Btn cmd="insertUnorderedList" icon={List} label="Lista con viñetas" />
        <Btn cmd="insertOrderedList" icon={ListOrdered} label="Lista numerada" />
      </div>
      <div ref={ref} contentEditable suppressContentEditableWarning
        onInput={emit} onBlur={emit}
        className="rte-area min-h-[180px] p-4 text-sm text-ink-800 leading-relaxed focus:outline-none"
        data-placeholder={placeholder} data-testid={`${testid}-area`} />
    </div>
  );
}
