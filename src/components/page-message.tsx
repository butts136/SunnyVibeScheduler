import type { PageMessage } from '@/lib/types';

export function PageMessageBanner({ message }: { message: PageMessage | null }) {
  if (!message) {
    return null;
  }
  return <div className={`page-message ${message.kind}`}>{message.text}</div>;
}
