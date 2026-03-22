"""
listener.py — Listener principal do obras-monitor.
1. Na inicialização: lê todo o histórico do grupo e grava na planilha.
2. Em seguida: monitora novas mensagens em tempo real.
Fotos são enviadas ao Google Drive com links na planilha.
"""

import asyncio
import logging
import os
import threading
from http.server import HTTPServer, BaseHTTPRequestHandler
from datetime import datetime, timezone, timedelta

from telethon import TelegramClient, events
from telethon.tl.types import MessageMediaPhoto

from parser import parse_message
from sheets import append_rows, upload_photo, ja_processado, marcar_processado, carregar_ids_processados

logging.basicConfig(
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)

BRASILIA   = timezone(timedelta(hours=-3))
API_ID     = int(os.environ["TELEGRAM_API_ID"])
API_HASH   = os.environ["TELEGRAM_API_HASH"]
CANAL      = os.environ["TELEGRAM_CANAL"]
SESSION    = "obra_monitor"
BATCH_SIZE = 100  # mensagens por lote no backfill


class HealthHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        self.send_response(200)
        self.end_headers()
        self.wfile.write(b"OK")
    def log_message(self, format, *args):
        pass


def start_http():
    port = int(os.environ.get("PORT", 10000))
    server = HTTPServer(("0.0.0.0", port), HealthHandler)
    server.serve_forever()


async def main():
    threading.Thread(target=start_http, daemon=True).start()
    logger.info("Servidor HTTP iniciado.")

    client = TelegramClient(SESSION, API_ID, API_HASH)
    await client.start()
    logger.info("Conectado ao Telegram.")

    canal_entity = await client.get_entity(CANAL)
    logger.info(f"Grupo: {getattr(canal_entity, 'title', CANAL)}")

    # ── 1. BACKFILL: lê todo o histórico ─────────────────────────────────
    await backfill(client, canal_entity)

    # ── 2. MONITORAMENTO em tempo real ───────────────────────────────────
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
        append_rows(rows)
        marcar_processado(msg.id)

    logger.info("Aguardando novas mensagens...")
    await client.run_until_disconnected()


async def backfill(client: TelegramClient, canal_entity):
    """
    Lê todas as mensagens do histórico do grupo em ordem cronológica.
    Pula mensagens já processadas (controle via arquivo local).
    """
    logger.info("Iniciando backfill do histórico...")

    # Carrega IDs já processados da planilha (uma única chamada à API)
    carregar_ids_processados()

    total_texto = 0
    total_fotos = 0
    total_skip  = 0

    # Coleta todas as mensagens (da mais recente para a mais antiga)
    mensagens = []
    async for msg in client.iter_messages(canal_entity, limit=None):
        mensagens.append(msg)

    # Inverte para processar em ordem cronológica
    mensagens.reverse()
    logger.info(f"Total de mensagens no histórico: {len(mensagens)}")

    for msg in mensagens:
        msg_id = msg.id

        # Pula se já foi processada em execução anterior
        if ja_processado(msg_id):
            total_skip += 1
            continue

        # Mensagem de foto
        if msg.media and isinstance(msg.media, MessageMediaPhoto):
            await _handle_photo(client, msg)
            total_fotos += 1
            marcar_processado(msg_id)
            continue

        # Mensagem de texto
        texto = msg.text
        if not texto:
            marcar_processado(msg_id)
            continue

        rows = parse_message(texto)
        if rows is None:
            marcar_processado(msg_id)
            continue

        data = rows[0].get("data", "?")
        logger.info(f"[backfill] {data} — {len(rows)} frente(s) — msg_id={msg_id}")
        append_rows(rows)
        marcar_processado(msg_id)
        total_texto += 1

        # Pequena pausa para não sobrecarregar a API do Google
        await asyncio.sleep(0.3)

    logger.info(
        f"Backfill concluído: {total_texto} diários, "
        f"{total_fotos} fotos, {total_skip} já processados."
    )


async def _handle_photo(client: TelegramClient, msg):
    """Baixa foto, faz upload ao Drive e loga o link."""
    try:
        photo_bytes = await client.download_media(msg.media, bytes)
        if not photo_bytes:
            return

        ts       = datetime.now(BRASILIA).strftime("%Y%m%d_%H%M%S")
        filename = f"obra_{ts}_{msg.id}.jpg"
        data_pasta = datetime.now(BRASILIA).strftime("%d-%m-%Y")

        link = upload_photo(photo_bytes, filename, data_pasta)
        if link:
            logger.info(f"Foto {filename} → {link}")
        else:
            logger.warning(f"Falha ao enviar foto {filename}.")
    except Exception as e:
        logger.error(f"Erro ao processar foto: {e}")


if __name__ == "__main__":
    asyncio.run(main())
