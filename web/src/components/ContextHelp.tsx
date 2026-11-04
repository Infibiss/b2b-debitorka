import { SupportContact } from './AccountHelp';
import { Dialog } from './Dialog';

export function ContextHelp({ onClose }: { onClose: () => void }) {
  return (
    <Dialog title="Обсудить сопровождение" onClose={onClose}>
      <p>
        Подготовьте реестр и документы по договору. Обсудим состав работы, условия и следующий шаг
        по делу.
      </p>
      <SupportContact />
    </Dialog>
  );
}
