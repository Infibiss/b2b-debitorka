import { renderToString } from 'react-dom/server';
import { PublicSite } from './components/PublicSite';

/** Server-rendered HTML of one public page; scripts/prerender.mjs sets the URL first. */
export function render() {
  return renderToString(<PublicSite />);
}
