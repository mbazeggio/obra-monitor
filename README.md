# Obra Monitor — Green Village

Listener Python que captura mensagens do grupo Telegram do diário de obras,
faz parse dos dados e grava em Google Sheets. Fotos são salvas no Google Drive
com links automáticos na planilha.

Usa **Telethon** (conta de usuário) — não requer permissão de administrador do grupo.

---

## Estrutura

```
obras_monitor/
├── listener.py       # Listener principal (Telethon)
├── gerar_sessao.py   # Roda UMA VEZ localmente para autenticar
├── parser.py         # Extração dos campos das mensagens
├── sheets.py         # Integração com Google Sheets e Google Drive
├── requirements.txt
├── render.yaml
└── README.md
```

---

## Planilha gerada (aba `diario`)

| Coluna            | Descrição                                          |
|-------------------|----------------------------------------------------|
| timestamp         | Data/hora (Brasília) do recebimento                |
| data              | Data da obra (ex: 16/03/2026)                      |
| condominio        | Nome do condomínio (ex: Green Village)             |
| bloco_local       | Bloco ou local (ex: Bloco A, Piscina)              |
| atividade         | Descrição da atividade                             |
| progresso_pct     | Percentual de conclusão                            |
| status            | em execução / pausada / planejada / concluída      |
| observacao        | Observação do dia sobre a atividade                |
| equipe            | Nomes e funções (ex: João Silva (Pintor))          |
| pessoas_canteiro  | Quantidade de pessoas no canteiro                  |
| clima_manha       | Clima da manhã (ex: névoa, chuva, sol)             |
| clima_tarde       | Clima da tarde                                     |
| vistoria_eng      | Vistoria do Engenheiro: Realizada / Não realizada  |
| fotos             | Links das fotos no Google Drive (separados por \|) |

---

## Passo 1 — Credenciais do Telegram

> Se você já tem o `obras_monitor.session` do agua-monitor, **não precisa refazer este passo** — basta renomear o arquivo.

1. Acesse [my.telegram.org](https://my.telegram.org) e faça login
2. Clique em **API development tools**
3. Preencha (App title: `obras-monitor`, Short name: `obrasmonitor`)
4. Copie o **api_id** e o **api_hash**

---

## Passo 2 — Gerar o arquivo de sessão (uma vez, localmente)

```bash
pip install telethon
python gerar_sessao.py
```

O script vai pedir `api_id`, `api_hash`, número de telefone e código SMS.
Ao final, cria o arquivo `obras_monitor.session`.

> Se quiser reaproveitar a sessão do agua-monitor:
> ```bash
> cp agua_monitor.session obras_monitor.session
> ```
> Mas edite o nome da SESSION no listener.py para bater com o nome do arquivo.

---

## Passo 3 — Google Sheets + Google Drive

### 3a. Service Account (se já tem do agua-monitor, reutilize)

1. Acesse [console.cloud.google.com](https://console.cloud.google.com)
2. Ative as APIs: **Google Sheets API** e **Google Drive API**
3. Vá em **IAM & Admin → Service Accounts → Create Service Account**
4. Na aba **Keys**, clique em **Add Key → Create new key → JSON**

### 3b. Criar a planilha

1. Crie uma nova planilha em [sheets.google.com](https://sheets.google.com)
2. Copie o **ID** da URL: `https://docs.google.com/spreadsheets/d/`**`SEU_ID`**`/edit`
3. Compartilhe com o e-mail da Service Account (`client_email` no JSON) como **Editor**

### 3c. Pasta no Google Drive

O script cria automaticamente a pasta `obras-monitor` no Drive da Service Account
com subpastas por data (ex: `16-03-2026`). Basta garantir que a API do Drive está ativa.

---

## Passo 4 — Deploy no Render

### 4a. Suba o código no GitHub

```bash
git init
git add .
git commit -m "inicial"
git remote add origin https://github.com/SEU_USUARIO/obras-monitor.git
git push -u origin main
```

### 4b. Crie o serviço no Render

1. Acesse [render.com](https://render.com) → **New → Web Service**
2. Conecte o repositório `obras-monitor`
3. Configure:
   - **Runtime:** Python 3
   - **Build Command:** `pip install -r requirements.txt`
   - **Start Command:** `python listener.py`
   - **Instance Type:** Free

### 4c. Variáveis de ambiente

| Variável             | Valor                                                  |
|----------------------|--------------------------------------------------------|
| `TELEGRAM_API_ID`    | Número obtido em my.telegram.org                       |
| `TELEGRAM_API_HASH`  | Hash obtido em my.telegram.org                         |
| `TELEGRAM_CANAL`     | Link do grupo (ex: `https://t.me/+omD6J2gKP2VjNThh`)  |
| `SPREADSHEET_ID`     | ID da planilha Google Sheets                           |
| `GOOGLE_CREDS_JSON`  | Conteúdo completo do JSON da Service Account           |
| `DRIVE_FOLDER_NAME`  | `obras-monitor` (ou outro nome de pasta no Drive)      |

### 4d. Enviar o arquivo de sessão

```bash
git add obras_monitor.session
git commit -m "adiciona sessao telethon"
git push
```

> Mantenha o repositório **privado** no GitHub.

---

## Dashboard no Looker Studio

1. Acesse [lookerstudio.google.com](https://lookerstudio.google.com)
2. **Criar → Relatório → Google Sheets** → sua planilha → aba `diario`
3. Sugestões de visualizações:
   - **Tabela** filtrada por data com todas as frentes do dia
   - **Gráfico de barras** de `progresso_pct` por `atividade` (evolução)
   - **Scorecard** contando atividades por status (em execução / pausadas)
   - **Filtro** por `bloco_local` para acompanhar Bloco A e B separadamente
   - **Linha do tempo** de clima e vistorias

---

## Troubleshooting

**"Session file not found" no Render:**
Confirme que `obras_monitor.session` foi commitado e enviado ao GitHub.

**Fotos não aparecem na planilha:**
As fotos são processadas individualmente quando enviadas no grupo.
Certifique-se de que a API do Google Drive está ativa e a Service Account tem permissão.

**Render suspende o serviço (plano gratuito):**
Configure um ping a cada 10 minutos no [cron-job.org](https://cron-job.org)
apontando para a URL do serviço Render.

**Mensagem não parseada:**
O parser só processa mensagens que contenham a palavra "Frentes:".
Mensagens de outro formato são ignoradas silenciosamente.
