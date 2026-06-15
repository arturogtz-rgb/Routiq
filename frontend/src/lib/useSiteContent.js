import { useEffect, useState } from 'react';
import api from '@/lib/api';

/**
 * Loads editable site content. When the URL has ?preview=1 and the user is a
 * super_admin (cookie auth), it loads the DRAFT; otherwise the PUBLISHED copy.
 * The backend always returns content merged with defaults, so every field exists.
 */
export function useSiteContent() {
  const [content, setContent] = useState(null);
  useEffect(() => {
    const preview = new URLSearchParams(window.location.search).get('preview') === '1';
    let cancelled = false;

    const fetchOnce = async () => {
      if (preview) {
        try {
          const { data } = await api.get('/site-settings');
          return data.draft;
        } catch (_e) { /* fall through to published */ }
      }
      const { data } = await api.get('/site-settings/public');
      return data;
    };

    (async () => {
      // Retry a few times with backoff so a single aborted/racey request right
      // after navigation never leaves us silently rendering FALLBACK defaults.
      for (let attempt = 0; attempt < 3; attempt += 1) {
        try {
          const data = await fetchOnce();
          if (!cancelled) setContent(data);
          return;
        } catch (_e) {
          if (cancelled) return;
          await new Promise((r) => setTimeout(r, 400 * (attempt + 1)));
        }
      }
    })();

    return () => { cancelled = true; };
  }, []);
  return content;
}
