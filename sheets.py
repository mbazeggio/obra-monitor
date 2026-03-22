"""
sheets.py — Gravação no Google Sheets e upload de fotos no Google Drive.
"""

import gspread
from google.oauth2.service_account import Credentials
from googleapiclient.discovery import build
from googleapiclient.http import MediaIoBaseUpload
import os
import json
import io
import logging

logger = logging.getLogger(__name__)

SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]

HEADER = [
    "timestamp", "data", "condominio",
    "bloco_local", "atividade", "progresso_pct", "status",
    "observacao", "equipe", "pessoas_canteiro",
    "clima_manha", "clima_tarde", "vistoria_eng",
    "fotos",
]

# Cache em memória dos IDs já processados
_cache_ids: set[str] | None = None


def _get_creds() -> Credentials:
    creds_json = os.environ["GOOGLE_CREDS_JSON"]
    creds_dict = json.loads(creds_json)
    return Credentials.from_service_account_info(creds_dict, scopes=SCOPES)


def _get_sheet(client: gspread.Client, spreadsheet_id: str) -> gspread.Worksheet:
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        sheet = spreadsheet.worksheet("diario")
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("diario", rows=10000, cols=len(HEADER))

    existing = sheet.row_values(1)
    if existing != HEADER:
        sheet.clear()
        sheet.append_row(HEADER, value_input_option="RAW")
        logger.info("Cabeçalho criado na aba 'diario'.")

    return sheet


def _get_controle_sheet(client: gspread.Client, spreadsheet_id: str) -> gspread.Worksheet:
    spreadsheet = client.open_by_key(spreadsheet_id)
    try:
        return spreadsheet.worksheet("_controle")
    except gspread.WorksheetNotFound:
        sheet = spreadsheet.add_worksheet("_controle", rows=50000, cols=1)
        sheet.append_row(["msg_id"], value_input_option="RAW")
        logger.info("Aba '_controle' criada na planilha.")
        return sheet


def append_rows(rows: list[dict]) -> bool:
    """Insere múltiplas linhas (uma por frente de trabalho) na planilha."""
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    try:
        creds  = _get_creds()
        client = gspread.authorize(creds)
        sheet  = _get_sheet(client, spreadsheet_id)

        for row_data in rows:
            row = [str(row_data.get(col, "")) for col in HEADER]
            sheet.append_row(row, value_input_option="USER_ENTERED")

        logger.info(f"{len(rows)} linha(s) inserida(s) na planilha.")
        return True
    except Exception as e:
        logger.error(f"Erro ao gravar no Sheets: {e}")
        return False


def carregar_ids_processados() -> set[str]:
    """
    Carrega todos os IDs já processados da aba '_controle'.
    Popula o cache em memória — chamado uma vez no início do backfill.
    """
    global _cache_ids
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    try:
        creds  = _get_creds()
        client = gspread.authorize(creds)
        sheet  = _get_controle_sheet(client, spreadsheet_id)
        valores = sheet.col_values(1)[1:]  # pula cabeçalho
        _cache_ids = set(valores)
        logger.info(f"{len(_cache_ids)} IDs já processados carregados da planilha.")
        return _cache_ids
    except Exception as e:
        logger.error(f"Erro ao carregar IDs processados: {e}")
        _cache_ids = set()
        return _cache_ids


def ja_processado(msg_id: int) -> bool:
    """Verifica no cache em memória se esta mensagem já foi gravada."""
    global _cache_ids
    if _cache_ids is None:
        carregar_ids_processados()
    return str(msg_id) in _cache_ids


def marcar_processado(msg_id: int) -> None:
    """Grava o ID na aba '_controle' e atualiza o cache."""
    global _cache_ids
    spreadsheet_id = os.environ["SPREADSHEET_ID"]
    id_str = str(msg_id)

    if _cache_ids is not None:
        _cache_ids.add(id_str)

    try:
        creds  = _get_creds()
        client = gspread.authorize(creds)
        sheet  = _get_controle_sheet(client, spreadsheet_id)
        sheet.append_row([id_str], value_input_option="RAW")
    except Exception as e:
        logger.error(f"Erro ao marcar ID {msg_id} como processado: {e}")


def upload_photo(photo_bytes: bytes, filename: str, data_str: str) -> str | None:
    """
    Faz upload de uma foto para o Google Drive.
    Organiza em subpastas: obras-monitor / data_str
    Retorna o link público do arquivo ou None em caso de erro.
    """
    drive_root_name = "obras-monitor"
    try:
        creds   = _get_creds()
        service = build("drive", "v3", credentials=creds)

        root_id      = _get_or_create_folder(service, drive_root_name, parent_id=None)
        subfolder_id = _get_or_create_folder(service, data_str, parent_id=root_id)

        file_metadata = {"name": filename, "parents": [subfolder_id]}
        media = MediaIoBaseUpload(
            io.BytesIO(photo_bytes),
            mimetype="image/jpeg",
            resumable=False,
        )
        uploaded = service.files().create(
            body=file_metadata,
            media_body=media,
            fields="id, webViewLink",
        ).execute()

        service.permissions().create(
            fileId=uploaded["id"],
            body={"type": "anyone", "role": "reader"},
        ).execute()

        link = uploaded.get("webViewLink", "")
        logger.info(f"Foto enviada ao Drive: {filename} → {link}")
        return link

    except Exception as e:
        logger.error(f"Erro ao fazer upload da foto: {e}")
        return None


def _get_or_create_folder(service, name: str, parent_id: str | None) -> str:
    """Retorna o ID de uma pasta no Drive, criando-a se não existir."""
    query = f"name='{name}' and mimeType='application/vnd.google-apps.folder' and trashed=false"
    if parent_id:
        query += f" and '{parent_id}' in parents"

    results = service.files().list(q=query, fields="files(id)").execute()
    files   = results.get("files", [])

    if files:
        return files[0]["id"]

    metadata = {"name": name, "mimeType": "application/vnd.google-apps.folder"}
    if parent_id:
        metadata["parents"] = [parent_id]

    folder = service.files().create(body=metadata, fields="id").execute()
    return folder["id"]
