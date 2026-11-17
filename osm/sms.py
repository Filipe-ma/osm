import requests
import logging
from django.conf import settings

logger = logging.getLogger(__name__)

def enviar_sms_mozesms(telefone: str, mensagem: str, sender: str = None) -> tuple:
    """
    Envia SMS via API da MozeSMS.
    Retorna (sucesso: bool, mensagem: str)
    """
    token = settings.MOZESMS_BEARER_TOKEN
    if not token:
        return False, "Token MozeSMS não configurado."

    sender_id = sender or settings.MOZESMS_SENDER_ID
    url = f"{settings.MOZESMS_API_BASE}/v1/sms/send"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    payload = {
        "from": sender_id,
        "to": telefone,
        "message": mensagem
    }

    try:
        response = requests.post(url, json=payload, headers=headers, timeout=30)
        response.raise_for_status()
        data = response.json()
        return True, data.get('message_id', 'Enviado')
    except requests.exceptions.RequestException as e:
        logger.error(f"Erro MozeSMS para {telefone}: {e}")
        return False, str(e)