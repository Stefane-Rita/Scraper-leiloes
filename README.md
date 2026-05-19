# Web Scraper — Leilões Copart & Sodré Santoro

Monitoramento automatizado de leilões ativos nos sites [Copart Brasil](https://www.copart.com.br/search/leil%C3%A3o/?displayStr=Leil%C3%A3o&from=%2FvehicleFinder) e [Sodré Santoro](https://www.sodresantoro.com.br/lotes/em-destaque?sort=auction_date_init_asc), com atualização periódica em **Google Planilhas**.

## Colunas na planilha

| Coluna | Descrição |
|--------|-----------|
| Fonte | Copart ou Sodré Santoro |
| Modelo do Veículo | Descrição do lote |
| Lance Atual | Maior lance atual |
| Preço Avaliado | Valor de avaliação (quando disponível) |
| Diferença em R$ | Avaliação − Lance |
| Diferença em % | Lance como % da avaliação |
| Data do Leilão | Início do leilão |
| Data de Finalização | Encerramento previsto |
| Oportunidade | **Sim** se lance ≤ 45% do avaliado |
| Condição do Veículo | Danos, sinistro, etc. |
| Condição do Leilão | Status / tipo de venda |
| Local do Leilão | Pátio / cidade |

## Arquitetura

```
main.py          → FastAPI (health) + agendador
src/pipeline.py  → Orquestra coleta e sync
src/scrapers/    → Copart (API interna) e Sodré (API search-lots)
src/sheets.py    → Google Sheets via Service Account
```

- **Copart**: após abrir a página no Chromium (Playwright), chama `POST /public/lots/search` com os cookies/sessão do navegador (contorna Incapsula).
- **Sodré Santoro**: `POST https://www.sodresantoro.com.br/api/search-lots` com filtro de leilões `aberto`/`online` e lotes em `andamento`.

## Pré-requisitos

- Python 3.11+
- Conta Google Cloud com **Service Account** e planilha compartilhada com o e-mail da conta

## Configuração da planilha (passo a passo)

Guia completo com prints e troubleshooting: **[docs/CONFIGURACAO_PLANILHA.md](docs/CONFIGURACAO_PLANILHA.md)**

Resumo rápido:

1. Google Cloud → ativar **Sheets API** + **Drive API** → criar **Service Account** → baixar JSON.
2. Criar planilha → **Compartilhar** com o `client_email` do JSON (Editor).
3. Copiar ID da URL → configurar `.env` (veja `.env.example`).
4. `python scripts/verificar_planilha.py` → `python scripts/sync_once.py`.

## Configuração local

1. Clone o repositório e instale dependências:

```bash
pip install -r requirements.txt
python -m playwright install chromium
```

2. Copie `.env.example` para `.env` e preencha (detalhes em `docs/CONFIGURACAO_PLANILHA.md`).

3. Testes:

```bash
python scripts/verificar_planilha.py   # só conexão Google
python scripts/dry_run.py              # scraping sem planilha
python scripts/sync_once.py            # uma atualização completa
python main.py                         # serviço contínuo
```

Acesse `http://localhost:8000/` para health check. `POST /run` dispara uma atualização manual.

## GitHub e deploy (sem expor o JSON)

Guia completo: **[docs/GITHUB_E_RAILWAY.md](docs/GITHUB_E_RAILWAY.md)** — init, commit seguro, push e Railway.

## Deploy no Railway

1. Envie o projeto para o GitHub (sem `.env` nem `credentials/`).
2. Crie um projeto no [Railway](https://railway.app) conectado ao repositório.
3. Configure as variáveis de ambiente (mesmas do `.env`).
4. O `railway.toml` instala Chromium e inicia `main.py`.
5. Use a URL pública `/` como health check.

> **Vercel** não é ideal para este projeto (Playwright + processo contínuo). Prefira **Railway**, Render ou um VPS.

## O que foi mais complicado / aprendizados

1. **Proteção anti-bot (Copart / Incapsula)** — Requisições HTTP diretas retornam challenge HTML. A solução foi usar Playwright para obter sessão válida e chamar a API interna via `fetch` no contexto da página.

2. **APIs não documentadas** — Ambos os sites expõem JSON em endpoints descobertos via interceptação de rede (`/public/lots/search` e `/api/search-lots`), em vez de parsear HTML.

3. **Preço avaliado no Sodré** — Veículos de frota muitas vezes **não trazem** avaliação na API; usamos regex em `lot_description` (comum em judiciais) e, quando aplicável, `bid_initial` como referência. Lotes sem avaliação aparecem como **Oportunidade: Indisponível**.

4. **Paginação Copart** — A API retorna ~10–20 itens por página; o scraper percorre várias páginas (`COPART_MAX_PAGES`) para cobrir mais lotes sem sobrecarregar o deploy.

5. **Google Sheets em tempo real** — “Tempo real” aqui significa atualização periódica (padrão: 5 min via `SCRAPE_INTERVAL_SECONDS`), reescrevendo a aba com timestamp na primeira linha.

## Estrutura do projeto

```
├── main.py
├── requirements.txt
├── src/
│   ├── models.py
│   ├── transform.py
│   ├── browser.py
│   ├── pipeline.py
│   ├── sheets.py
│   └── scrapers/
│       ├── copart.py
│       └── sodre.py
└── scripts/
    ├── dry_run.py
    └── discover_apis.py
```

## Licença

Projeto de desafio técnico — uso educacional. Respeite os termos de uso dos sites leiloeiros.
