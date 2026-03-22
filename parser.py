"""
parser.py — Extrai campos das mensagens do diário de obras do Telegram.
Formato esperado: mensagens do grupo Green Village com frentes de trabalho.
"""

import re
from datetime import datetime, timezone, timedelta

BRASILIA = timezone(timedelta(hours=-3))


def parse_message(text: str) -> list[dict] | None:
    """
    Recebe o texto de uma mensagem do Telegram (diário de obras).
    Retorna uma lista de dicionários (uma entrada por frente de trabalho),
    ou None se a mensagem não for do diário.
    """
    # Filtra mensagens que não são do diário
    if "Frentes:" not in text and "frentes:" not in text.lower():
        return None

    # --- Cabeçalho ---
    condominio = _extract(r'^([A-Za-zÀ-ÿ\s]+)\s+Data:', text) or "Green Village"
    data_str   = _extract(r'Data:\s*(\d{2}/\d{2}/\d{4})', text) or ""
    clima_manha = _extract(r'Manha[ã]?:\s*([^\|]+)', text, strip=True) or ""
    clima_tarde = _extract(r'Tarde:\s*([^\n]+)', text, strip=True) or ""
    vistoria    = _extract(r'Vistoria do Engenheiro:\s*([^\n]+)', text, strip=True) or ""

    timestamp = datetime.now(BRASILIA).isoformat()

    # --- Frentes de trabalho ---
    frentes = _parse_frentes(text)

    if not frentes:
        return None

    rows = []
    for f in frentes:
        row = {
            "timestamp":        timestamp,
            "data":             data_str,
            "condominio":       condominio.strip(),
            "bloco_local":      f.get("bloco", ""),
            "atividade":        f.get("atividade", ""),
            "progresso_pct":    f.get("progresso", ""),
            "status":           f.get("status", ""),
            "observacao":       f.get("observacao", ""),
            "equipe":           f.get("equipe", ""),
            "pessoas_canteiro": f.get("pessoas_canteiro", ""),
            "clima_manha":      clima_manha,
            "clima_tarde":      clima_tarde,
            "vistoria_eng":     vistoria,
            "fotos":            "",  # preenchido pelo listener após upload
        }
        rows.append(row)

    return rows


def _extract(pattern: str, text: str, strip: bool = False) -> str | None:
    m = re.search(pattern, text, re.IGNORECASE | re.MULTILINE)
    if m:
        val = m.group(1)
        return val.strip() if strip else val
    return None


def _parse_frentes(text: str) -> list[dict]:
    """
    Divide o texto em blocos por frente de trabalho e extrai campos de cada um.
    Estratégia: separa blocos pelo padrão "Bloco X - " ou "Local -"
    """
    frentes = []

    # Isola a seção de frentes
    frentes_match = re.search(r'Frentes:(.*?)(?:Clima:|Vistoria|$)', text, re.DOTALL | re.IGNORECASE)
    if not frentes_match:
        return frentes

    frentes_text = frentes_match.group(1)

    # Divide em blocos individuais de atividade
    # Um novo bloco começa quando aparece "Bloco X -" ou uma linha que começa com local conhecido
    blocos_raw = re.split(r'\n(?=\s*(?:Bloco\s+[A-Z]|[A-Z][a-z]+\s+[A-Z])\s*-)', frentes_text)

    bloco_atual = None

    for bloco in blocos_raw:
        bloco = bloco.strip()
        if not bloco:
            continue

        # Detecta cabeçalho do bloco: "Bloco A - Descrição da atividade - XX% (status)"
        header = re.match(
            r'(Bloco\s+\w+|[A-Za-zÀ-ÿ\s]+?)\s*-\s*(.+?)\s*-\s*(\d+)%\s*\(([^)]+)\)',
            bloco
        )

        if header:
            bloco_atual = header.group(1).strip()
            atividade   = header.group(2).strip()
            progresso   = int(header.group(3))
            status      = header.group(4).strip()

            # Observação: linha logo após o header (sem "Equipe:")
            obs_match = re.search(
                r'\)\s*\n\s*-?\s*([^\n]+?)(?:\nEquipe:|\nBloco|\Z)',
                bloco, re.DOTALL
            )
            observacao = obs_match.group(1).strip() if obs_match else ""
            # Remove hífens ou traços iniciais
            observacao = re.sub(r'^[-–]\s*', '', observacao)

            # Equipe nomeada
            equipe_block = re.search(r'Equipe:(.*?)(?:\n\s*\n|\Z)', bloco, re.DOTALL)
            equipe_str, pessoas = _parse_equipe(equipe_block.group(1) if equipe_block else "")

            frentes.append({
                "bloco":            bloco_atual,
                "atividade":        atividade,
                "progresso":        progresso,
                "status":           status,
                "observacao":       observacao,
                "equipe":           equipe_str,
                "pessoas_canteiro": pessoas,
            })
        else:
            # Pode ser uma atividade adicional dentro do mesmo bloco (sem repetir o bloco)
            sub = re.match(r'\s*(.+?)\s*-\s*(\d+)%\s*\(([^)]+)\)', bloco)
            if sub and bloco_atual:
                atividade = sub.group(1).strip()
                progresso = int(sub.group(2))
                status    = sub.group(3).strip()

                obs_match = re.search(
                    r'\)\s*\n\s*-?\s*([^\n]+?)(?:\nEquipe:|\Z)',
                    bloco, re.DOTALL
                )
                observacao = obs_match.group(1).strip() if obs_match else ""
                observacao = re.sub(r'^[-–]\s*', '', observacao)

                equipe_block = re.search(r'Equipe:(.*?)(?:\n\s*\n|\Z)', bloco, re.DOTALL)
                equipe_str, pessoas = _parse_equipe(equipe_block.group(1) if equipe_block else "")

                frentes.append({
                    "bloco":            bloco_atual or "",
                    "atividade":        atividade,
                    "progresso":        progresso,
                    "status":           status,
                    "observacao":       observacao,
                    "equipe":           equipe_str,
                    "pessoas_canteiro": pessoas,
                })

    return frentes


def _parse_equipe(equipe_text: str) -> tuple[str, str]:
    """
    Retorna (lista_de_nomes_e_funcoes, numero_pessoas_no_canteiro).
    Ex: "JOÃO SILVA - Pintor; PEDRO - Ajudante", "2"
    """
    if not equipe_text:
        return "", ""

    # Verifica se tem apenas "X pessoas no canteiro" (sem nomes)
    apenas_count = re.search(r'(\d+)\s+pessoas?\s+no\s+canteiro', equipe_text, re.IGNORECASE)

    # Extrai membros nomeados: NOME SOBRENOME - Função
    membros = re.findall(
        r'([A-ZÁÉÍÓÚÀÂÊÔÃÕÇ][A-ZÁÉÍÓÚÀÂÊÔÃÕÇ\s]+?)\s*-\s*([A-Za-zÀ-ÿ\s]+?)(?=\n|$)',
        equipe_text
    )

    # Filtra falsos positivos (ex: match do próprio "X pessoas no canteiro")
    membros = [(n.strip(), f.strip()) for n, f in membros
               if len(n.strip()) > 3 and "pessoas" not in n.lower()]

    equipe_str = "; ".join(f"{n} ({f})" for n, f in membros)
    pessoas = str(len(membros)) if membros else (apenas_count.group(1) if apenas_count else "")

    return equipe_str, pessoas
