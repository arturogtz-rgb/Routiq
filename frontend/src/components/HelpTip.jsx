import { HelpCircle } from 'lucide-react';
import { Tooltip, TooltipContent, TooltipProvider, TooltipTrigger } from '@/components/ui/tooltip';

export const HelpTip = ({ text, testid }) => (
  <TooltipProvider delayDuration={150}>
    <Tooltip>
      <TooltipTrigger asChild>
        <button type="button" className="inline-flex align-middle ml-1 text-ink-300 hover:text-brand-500 transition-colors" aria-label="Ayuda" data-testid={testid}>
          <HelpCircle className="w-3.5 h-3.5" />
        </button>
      </TooltipTrigger>
      <TooltipContent className="max-w-xs bg-ink-900 text-white leading-relaxed">{text}</TooltipContent>
    </Tooltip>
  </TooltipProvider>
);
