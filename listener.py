"""
listener.py — Listener principal do obra-monitor.
1. Na inicialização: lê todo o histórico do grupo e grava na planilha.
2. Em seguida: monitora novas mensagens em tempo real.
"""

import asyncio
import logging
import os
import threading
from datetime import datetime, timezone, timedelta
from http.server import HTTPServer, BaseHTTPRequestHandler

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto

from parser import parse_message
from sheets import append_rows, upload_photo, ja_processado, marcar_processado, carregar_ids_processados

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BRASILIA = timezone(timedelta(hours=-3))
API_ID   = int(os.environ["TELEGRAM_API_ID"])
API_HASH = os.environ["TELEGRAM_API_HASH"]
CANAL    = os.environ["TELEGRAM_CANAL"]
SESSION  = "obra_monitor"


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass


def start_http():
    port = int(os.environ.get("PORT", 10000))
    HTTPServer(("0.0.0.0", port), HealthHandler).serve_forever()


async def main():
    threading.Thread(target=start_http, daemon=True).start()
    logger.info("Servidor HTTP iniciado.")

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    logger.info("Conectado ao Telegram.")

    canal_entity = await client.get_entity(CANAL)
    logger.info(f"Grupo: {getattr(canal_entity, 'title', CANAL)}")

    await backfill(client, canal_entity)

    logger.info("Iniciando monitoramento em tempo real...")

    @client.on(events.NewMessage(chats=canal_entity))
    async def handler(event):
        msg = event.message

        if msg.media and isinstance(msg.media, MessageMediaPhoto):
            await _handle_photo(client, msg)
            return

        texto = msg.text
        if not texto:
            return

        rows = parse_message(texto)
        if rows is None:
            return

        logger.info(f"Nova mensagem — {rows[0].get('data','')} — {len(rows)} frente(s)")
        ok = append_rows(rows)
        if ok:
            marcar_processado(msg.id)
        else:
            logger.error(f"Falha ao gravar mensagem {msg.id}.")

    logger.info("Aguardando novas mensagens...")
    await client.run_until_disconnected()


async def backfill(client: TelegramClient, canal_entity):
    logger.info("Iniciando backfill do histórico...")
    carregar_ids_processados()

    total_texto = total_fotos = total_skip = 0

    mensagens = []
    async for msg in client.iter_messages(canal_entity, limit=None):
        mensagens.append(msg)
    mensagens.reverse()
    logger.info(f"Total de mensagens no histórico: {len(mensagens)}")

    for msg in mensagens:
        if ja_processado(msg.id):
            total_skip += 1
            continue

        msg_ts = msg.date.astimezone(BRASILIA)

        # Foto
        if msg.media and isinstance(msg.media, MessageMediaPhoto):
            ok = await _handle_photo(client, msg)
            if ok:
                marcar_processado(msg.id)
                total_fotos += 1
            else:
                logger.warning(f"[backfill] Falha ao enviar foto msg_id={msg.id} — será reprocessada.")
            continue

        # Texto irrelevante
        texto = msg.text
        if not texto:
            marcar_processado(msg.id)
            continue

        # Parse
        rows = parse_message(texto)
        if rows is None:
            marcar_processado(msg.id)
            continue

        # Grava — só marca como processado se gravou com sucesso
        data = rows[0].get("data", "?")
        logger.info(f"[backfill] {data} — {len(rows)} frente(s) — msg_id={msg.id}")
        ok = append_rows(rows)
        if ok:
            marcar_processado(msg.id)
            total_texto += 1
        else:
            logger.warning(f"[backfill] Falha ao gravar msg_id={msg.id} — será reprocessado.")

        await asyncio.sleep(0.3)

    logger.info(
        f"Backfill concluído: {total_texto} diários, "
        f"{total_fotos} fotos, {total_skip} já processados."
    )


async def _handle_photo(client: TelegramClient, msg) -> bool:
    """Baixa e faz upload da foto. Retorna True em caso de sucesso."""
    try:
        photo_bytes = await client.download_media(msg.media, bytes)
        if not photo_bytes:
            return False

        msg_ts     = msg.date.astimezone(BRASILIA)
        data_pasta = msg_ts.strftime("%d-%m-%Y")
        filename   = f"obra_{msg_ts.strftime('%Y%m%d_%H%M%S')}_{msg.id}.jpg"

        link = upload_photo(photo_bytes, filename, data_pasta)
        if link:
            logger.info(f"Foto {filename} → {link}")
            return True
        return False
    except Exception as e:
        logger.error(f"Erro ao processar foto: {e}")
        return False


if __name__ == "__main__":
    asyncio.run(main())
