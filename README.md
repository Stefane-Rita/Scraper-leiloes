# Web Scraper — Leilões Copart & Sodré Santoro

Monitoramento automatizado de leilões de veículos nos sites [Copart Brasil](https://www.copart.com.br/search/leil%C3%A3o/?displayStr=Leil%C3%A3o&from=%2FvehicleFinder) e [Sodré Santoro](https://www.sodresantoro.com.br/veiculos/lotes?sort=auction_date_init_asc), com enriquecimento de preços via **Tabela FIPE** e atualização periódica em **Google Planilhas**.

---

## Colunas na planilha

| Coluna | Descrição |
|--------|-----------|
| Fonte | Copart ou Sodré Santoro |
| Modelo do Veículo | Descrição do lote |
| Lance Atual | Maior lance registrado |
| Preço Avaliado | Valor de avaliação (FIPE quando não disponível no site) |
| Diferença em R$ | Avaliação − Lance |
| Diferença em % | Lance como % da avaliação |
| Data do Leilão | Início do leilão |
| Data de Finalização | Encerramento previsto |
| Oportunidade | **Sim** se lance ≤ 45% do avaliado |
| Condição do Veículo | Danos, sinistro, origem |
| Condição do Leilão | Status / tipo de venda |
| Local do Leilão | Pátio / cidade |

> A aba **FIPE_Cache** é criada automaticamente na planilha para guardar os preços consultados (válidos por 30 dias), evitando chamadas repetidas à API FIPE.

---

## Arquitetura

```
scripts/
└── run_cron.py       → Ponto de entrada do cron job no Railway

src/
├── pipeline.py       → Orquestra coleta, enriquecimento e sync
├── scrapers/
│   ├── copart.py     → Copart via interceptação de API interna
│   └── sodre.py      → Sodré via POST /api/search-lots
├── fipe.py           → Cliente HTTP para a API FIPE (fuzzy match + cache em memória)
├── fipe_enricher.py  → Enriquece lotes Sodré sem preço via FIPE + cache no Sheets
├── sheets.py         → Google Sheets via Service Account
├── browser.py        → Sessão Playwright (Chromium headless)
├── models.py         → Dataclass AuctionLot
├── filters.py        → Filtros de lotes ativos
└── transform.py      → Parsing, formatação e cálculos
```

**Copart** — após abrir a página no Chromium (Playwright), intercepta as respostas de `POST /public/lots/search` com os cookies/sessão do navegador, contornando a proteção Incapsula.

**Sodré Santoro** — chama `POST /api/search-lots` com filtro de leilões `aberto`/`online` e lotes em `andamento`, paginando até cobrir todos os ativos.

**FIPE** — para lotes Sodré sem preço avaliado, consulta a [API FIPE](https://fipe.parallelum.com.br/api/v2) com matching fuzzy (marca → modelo → ano) e persiste o resultado em cache no Sheets por 30 dias.

---

## Pré-requisitos

- Python 3.11+
- Conta Google Cloud com **Service Account** e planilha compartilhada com o e-mail da conta
- Token gratuito da [FIPE API](https://fipe.online/register) (1.000 req/dia — necessário para o volume do cron)

---

## Configuração da planilha

1. Google Cloud → ativar **Sheets API** + **Drive API** → criar **Service Account** → baixar JSON.
2. Criar planilha → **Compartilhar** com o `client_email` do JSON (permissão: Editor).
3. Copiar o ID da URL da planilha → configurar as variáveis de ambiente (veja `.env.example`).
4. Testar localmente:
   ```bash
   python scripts/verificar_planilha.py
   python scripts/sync_once.py
   ```

---

## Configuração local

```bash
# 1. Clone e instale dependências
pip install -r requirements.txt
python -m playwright install chromium
python -m playwright install-deps chromium

# 2. Configure o ambiente
cp .env.example .env
# Preencha GOOGLE_SHEETS_CREDENTIALS_JSON, GOOGLE_SPREADSHEET_ID e FIPE_API_TOKEN

# 3. Scripts de teste
python scripts/verificar_planilha.py   # testa conexão com o Sheets
python scripts/dry_run.py              # scraping sem gravar na planilha
python scripts/sync_once.py            # execução completa única
```

---

## Variáveis de ambiente

| Variável | Descrição |
|----------|-----------|
| `GOOGLE_SHEETS_CREDENTIALS_JSON` | Conteúdo completo do JSON da Service Account |
| `GOOGLE_SPREADSHEET_ID` | ID da planilha (extraído da URL) |
| `GOOGLE_WORKSHEET_NAME` | Nome da aba principal (padrão: `Leilões`) |
| `FIPE_API_TOKEN` | Token de acesso à API FIPE (gratuito em fipe.online) |
| `COPART_MAX_PAGES` | Limite de páginas a percorrer na Copart (padrão: `50`) |
| `SODRE_MAX_PAGES` | Limite de páginas na Sodré (padrão: `30`) |

---

## Deploy no Railway

O projeto roda como **Cron Service** no Railway, executando `scripts/run_cron.py` de forma autônoma — sem servidor HTTP, sem healthcheck, sem processo em background.

### `railway.toml`
```toml
[deploy]
startCommand = "python scripts/run_cron.py"
restartPolicyType = "ON_FAILURE"
cronSchedule = "0 * * * *"
```

### `nixpacks.toml`
```toml
[phases.setup]
nixPkgs = ["chromium", "nss", "at-spi2-atk", "libdrm", "libxkbcommon"]

[phases.install]
cmds = [
  "pip install -r requirements.txt",
  "python -m playwright install chromium",
  "python -m playwright install-deps chromium"
]

[start]
cmd = "python scripts/run_cron.py"
```

### Variáveis no Railway
Configure em **Variables** os mesmos nomes da tabela acima. Atenção: o nome `GOOGLE_SHEETS_CREDENTIALS_JSON` deve ser exato (com `SHEETS_`).

---

## Estrutura do projeto

```
├── scripts/
│   ├── run_cron.py          ← entrada do cron Railway
│   ├── dry_run.py
│   ├── sync_once.py
│   └── verificar_planilha.py
├── src/
│   ├── models.py
│   ├── transform.py
│   ├── filters.py
│   ├── browser.py
│   ├── pipeline.py
│   ├── fipe.py
│   ├── fipe_enricher.py
│   ├── sheets.py
│   └── scrapers/
│       ├── copart.py
│       └── sodre.py
├── railway.toml
├── nixpacks.toml
└── requirements.txt
```

---

## Ferramentas e ambiente de desenvolvimento

| Ferramenta | Uso |
|------------|-----|
| [Cursor](https://cursor.sh) | IDE principal — agente de IA integrado |
| [GitHub Codespaces](https://github.com/features/codespaces) | Ambiente de desenvolvimento em nuvem |
| [GitHub Copilot](https://github.com/features/copilot) | Assistência inline durante o desenvolvimento |
| [Claude (Anthropic)](https://claude.ai) | Revisão de arquitetura, diagnóstico de erros e geração de código |

> O projeto foi desenvolvido com assistência ativa de agentes de IA em todas as etapas — desde a descoberta das APIs não documentadas até o diagnóstico dos problemas de deploy no Railway.

---

## Minha experiência com o projeto

        Nunca havia realizado nenhum processo desse tipo — conhecia os conceitos, 
    mas nunca os tinha colocado em prática. O projeto foi possível com o auxílio 
    de agentes de IA como o Cursor (mesmo na versão gratuita limitada), o Copilot 
    integrado ao GitHub e o Claude.

        Para mim, a parte mais difícil foi resolver os problemas de hospedagem. Testei 
    todas as opções disponíveis: o Vercel, plataforma com a qual já tinha alguma 
    familiaridade, mostrou-se limitado demais para os requisitos do projeto. Migrar 
    para o Railway trouxe novos desafios — além da falta de familiaridade com a 
    plataforma, havia erros no código que faziam o processo encerrar prematuramente 
    (detalhados no tópico 2 abaixo), e adequar tudo para funcionar corretamente 
    consumiu mais tempo do que eu gostaria.

        Em termos pessoais, foi um projeto do qual realmente gostei. Poder testar tantas 
    tecnologias diferentes e chegar a um resultado funcional e satisfatório traz uma 
    alegria genuína — especialmente sendo uma pessoa iniciante. Precisei me aprofundar 
    em praticamente todos os temas envolvidos, já que partia apenas de um entendimento 
    conceitual dos passos necessários. No geral, fico feliz de ter participado da 
    seleção e de ter tido a oportunidade de mergulhar em um assunto tão interessante.

---

## O que foi mais complicado e aprendizados

### 1. APIs não documentadas
Nenhum dos dois sites possui API pública. Os endpoints `/public/lots/search` (Copart) e `/api/search-lots` (Sodré) foram descobertos via interceptação de rede nas DevTools do navegador — uma etapa essencial que antecede qualquer implementação.

### 2. Arquitetura errada no Railway (o bug principal)
O deploy inicial usava `main.py` com servidor FastAPI + `healthcheckPath` configurado. O Railway interpretava o healthcheck como "job concluído" e matava o processo em ~2 segundos — antes do pipeline terminar. A correção foi criar `scripts/run_cron.py` como ponto de entrada dedicado, sem servidor HTTP, deixando o processo encerrar naturalmente com `sys.exit(0)`.

### 3. Preço avaliado ausente no Sodré Santoro
Boa parte dos veículos de frota não traz avaliação na API. A primeira abordagem usou regex em `lot_description` e `bid_initial` como fallback. A solução definitiva foi integrar a Tabela FIPE com matching fuzzy (normalização de texto + `difflib`) para casar marca/modelo/ano entre os dados do Sodré e os identificadores FIPE, com cache persistente no Sheets para não ultrapassar o limite de requisições.

### 4. Gerenciamento do limite de requisições FIPE
A API FIPE tem limite de 1.000 req/dia no plano gratuito. Com execuções horárias e dezenas de veículos únicos por run, o custo acumula rapidamente. A solução foi um cache de 30 dias em aba separada do próprio Google Sheets: na primeira execução do mês os preços são consultados; nas demais, lidos do cache sem tocar na API.

---

## Licença

Projeto de estudo — uso educacional. Respeite os termos de uso dos sites leiloeiros.