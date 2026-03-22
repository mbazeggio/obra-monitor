"""
Execute este script UMA VEZ na sua máquina local antes do deploy.
Ele gera o arquivo 'obras_monitor.session' que deve ser enviado ao Render.

Uso:
    pip install telethon
    python gerar_sessao.py
"""
import asyncio
from telethon import TelegramClient

API_ID   = input("Cole seu API_ID (número): ").strip()
API_HASH = input("Cole seu API_HASH: ").strip()

async def main():
    client = TelegramClient("obras_monitor", int(API_ID), API_HASH)
    await client.start()
    print("\nSessão gerada com sucesso: arquivo 'obras_monitor.session' criado.")
    print("Faça upload deste arquivo no Render conforme instruído no README.")
    await client.disconnect()

asyncio.run(main())
