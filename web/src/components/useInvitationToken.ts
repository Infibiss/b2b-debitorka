import { useEffect, useState } from 'react';

/** Hash invitation links can change without loading a new document. */
export function useInvitationToken() {
  const [, refresh] = useState(0);
  useEffect(() => {
    const changed = () => refresh((value) => value + 1);
    window.addEventListener('hashchange', changed);
    window.addEventListener('popstate', changed);
    return () => {
      window.removeEventListener('hashchange', changed);
      window.removeEventListener('popstate', changed);
    };
  }, []);
  return (
    new URLSearchParams(location.hash.slice(1)).get('invite') ||
    new URLSearchParams(location.search).get('invite')
  );
}
