"""Telephony boundary. Preparing a request never dials or reserves paid work.

SpeechKit is a speech engine, not a telephone transport. Install a reviewed
provider adapter at get_voice_call_adapter; credentials alone cannot enable it.
"""
from dataclasses import asdict, dataclass
from typing import Protocol


@dataclass(frozen=True)
class CallRequest:
    tenant_id: str
    actor_id: str
    invoice_id: str
    phone: str
    contact_authorized: bool


@dataclass(frozen=True)
class Readiness:
    ready: bool
    status: str
    provider: str | None
    message: str
    setup_steps: tuple[str, ...]

    def public(self):
        return asdict(self)


class VoiceCallAdapter(Protocol):
    def readiness(self, tenant_id: str) -> Readiness: ...

    # A future dispatch implementation must recheck authorization, policy,
    # contact limits, idempotency and the financial snapshot before dialing.
    # It must return a provider receipt and handle uncertain outcomes explicitly.
    def start_call(self, request: CallRequest, *, idempotency_key: str) -> dict: ...


class UnconnectedVoiceCallAdapter:
    def readiness(self, tenant_id: str) -> Readiness:
        return Readiness(
            ready=False, status='adapter_required', provider=None,
            message='Подключите исходящий номер и телефонию организации в настройках звонков.',
            setup_steps=(
                'Выбрать существующую телефонию организации и передать администратору документацию разрешённого API или SIP-подключения.',
                'Подготовить исходящий номер, разрешённые направления, полномочия на контакт и правила записи разговоров.',
                'Подключить адаптер к Mandato: секреты только на сервере, привязка к организации, статусы звонка и проверка подлинности событий.',
                'Согласовать расписание и лимиты контакта, повторную проверку запретов, защиту от повторных вызовов и передачу разговора сотруднику.',
                'Проверить соединение на согласованном номере и принять результат до включения исходящих звонков.',
            ),
        )

    def start_call(self, request: CallRequest, *, idempotency_key: str) -> dict:
        raise RuntimeError('Telephony adapter is not connected')


def get_voice_call_adapter() -> VoiceCallAdapter:
    """Single integration point; no environment flag can impersonate a provider."""
    return UnconnectedVoiceCallAdapter()
