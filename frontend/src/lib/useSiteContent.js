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
    (async () => {
      try {
        if (preview) {
          const { data } = await api.get('/site-settings');
          setContent(data.draft);
          return;
        }
        const { data } = await api.get('/site-settings/public');
        setContent(data);
      } catch (_e) {
        try { const { data } = await api.get('/site-settings/public'); setContent(data); }
        catch (_e2) { setContent(null); }
      }
    })();
  }, []);
  return content;
}
