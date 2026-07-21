# promo-bot

Bot que roda de graça via GitHub Actions (a cada 6 horas) e manda alerta
no Telegram de duas formas:

1. **`product_watches`** — acompanha uma página de produto específica
   (ex: o ASUS Vivobook Go 15 na Amazon) e avisa quando o preço cai
   abaixo de um teto que você define.
2. **`deal_watches`** — vasculha categorias inteiras do Promobit
   (notebooks, notebook gamer, smartwatch, AirPods, TVs, etc.) e avisa
   só das ofertas que realmente valem a pena: desconto grande, preço
   abaixo de um teto, ou que o próprio Promobit já marcou com a tag
   "Menor preço".

## Estrutura do projeto

```
├── main.py                 # ponto de entrada: lê config, checa tudo, salva estado
├── config.json             # o que monitorar (produtos e categorias)
├── state.json              # memória do "já avisei sobre isso" (commitado pelo workflow)
├── debug_fetch.py          # testa o parser de uma categoria sem mandar alerta
├── debug_coupon.py         # testa a extração de cupom de uma oferta específica
├── requirements.txt
├── scraper/
│   ├── sources.py          # extrai preço de página de produto (Amazon, KaBuM, genérico)
│   ├── deals.py            # extrai/filtra ofertas e pega o cupom da página da oferta
│   └── telegram.py         # envio de mensagem via Telegram Bot API
└── .github/workflows/
    └── check_prices.yml    # agendamento (cron a cada 6h) e execução no Actions
```

## Como configurar

### 1. Criar o bot no Telegram
1. Fale com **@BotFather** no Telegram.
2. Mande `/newbot`, escolha um nome e um username (precisa terminar em `bot`).
3. Ele te dá um **token** — copia, você vai precisar dele.
4. Mande qualquer mensagem para o seu bot recém-criado (só pra ele "te conhecer").
5. Acesse no navegador:
   `https://api.telegram.org/bot<SEU_TOKEN>/getUpdates`
   e procure por `"chat":{"id": ...}` — esse número é o seu `chat_id`.

### 2. Configurar os secrets neste repositório
O código já está neste repositório — falta só cadastrar as credenciais.
Vá em **Settings → Secrets and variables → Actions → New repository secret**
e adicione:

- `TELEGRAM_BOT_TOKEN` = o token do passo 1
- `TELEGRAM_CHAT_ID` = o chat_id do passo 1

### 3. Editar o que monitorar

Tudo fica em `config.json`.

**Produtos específicos** (`product_watches`): `name` (identifica no
alerta), `url` (link do produto) e `price_threshold` (preço em reais —
avisa quando o preço atual for igual ou menor que esse valor).

```json
{
  "name": "Acer Swift Go 14 (Ryzen 7, 16GB, 512GB) - KaBuM",
  "url": "https://www.kabum.com.br/produto/XXXXX/...",
  "price_threshold": 4000
}
```

**Categorias inteiras** (`deal_watches`): já vem configurado com
Notebook (filtrado pra Ryzen 5/7 + 16GB), Notebook Gamer, Apple Watch,
AirPods, Hardware/periféricos, TVs, Cuecas e Meias. Cada watch aceita:

- `url` — link da categoria no Promobit (formato
  `https://www.promobit.com.br/promocoes/{categoria}/s/` — dá pra achar
  o slug certo navegando pelo menu de categorias do site)
- `keywords_all` *(opcional)* — todas essas palavras precisam aparecer
  no título da oferta
- `keywords_any` *(opcional)* — pelo menos uma dessas precisa aparecer
- `max_price` *(opcional)* — teto de preço em reais (limite rígido:
  acima disso a oferta é descartada)
- `min_discount_pct` *(opcional)* — desconto mínimo (%) pra considerar
  a oferta "muito boa"

**O desconto é o critério decisivo.** Quando você define
`min_discount_pct`, a oferta só passa se tiver um desconto **visível e
≥ esse valor** — não adianta só ter preço baixo ou estar marcada como
"Menor preço". Somado a isso, se você definiu `keywords_all`/
`keywords_any` o título precisa bater com elas, e se definiu `max_price`
a oferta não pode passar do teto. Ou seja: só chega no Telegram o que é
realmente um descontão. (Se um watch **não** tiver `min_discount_pct`,
ele volta ao modo permissivo antigo: passa por preço abaixo do teto ou
pela tag "Menor preço".)

**Cupons.** Quando a oferta usa cupom, o bot abre a página da oferta,
extrai o código e manda junto no alerta (ex: `🎟️ Cupom: BAIXOU15`) — dá
pra copiar direto no Telegram. Se ele identificar que é oferta de cupom
mas não conseguir ler o código, avisa mesmo assim (`🎟️ Precisa de cupom
(ver na página)`). Isso é feito só para as ofertas que já passaram no
filtro, então não pesa no número de requisições. Vale lembrar que o
desconto exibido na listagem pode ou não já incluir o cupom — se não
incluir, uma oferta boa só com cupom pode não bater o `min_discount_pct`
e acabar não sendo avisada.

Exemplo pra adicionar uma nova categoria (ex: caixa de som):

```json
{
  "name": "Caixa de som",
  "url": "https://www.promobit.com.br/promocoes/caixa-de-som/s/",
  "min_discount_pct": 40
}
```

### Testar o parser sem mandar alerta

Antes de confiar no scraping, dá pra ver o que ele está achando numa
categoria sem disparar nada no Telegram:

```bash
pip install -r requirements.txt
python debug_fetch.py https://www.promobit.com.br/promocoes/notebooks/s/
```

E pra conferir se a extração de cupom está funcionando numa oferta
específica (também sem mandar nada pro Telegram):

```bash
python debug_coupon.py https://www.promobit.com.br/oferta/....
```

### 4. Rodar
- O workflow já roda sozinho a cada 6 horas (horário UTC, então ajusta a
  expectativa de fuso se quiser mudar o cron em
  `.github/workflows/check_prices.yml`).
- Pra testar na hora: vai na aba **Actions** do repositório, escolhe
  "Check notebook prices" e clica em **Run workflow**.
- A cada execução o workflow commita o `state.json` atualizado de volta
  no repositório — é assim que o bot lembra do que já avisou.

## Testar localmente (opcional)

```bash
pip install -r requirements.txt
export TELEGRAM_BOT_TOKEN="seu_token"
export TELEGRAM_CHAT_ID="seu_chat_id"
python main.py
```

## Limitações importantes

- **Amazon** tem proteção anti-bot. Rodando a cada 6h o risco de bloqueio
  é baixo, mas se um dia o scraper parar de achar preço nela, é
  provavelmente isso — não tem solução 100% garantida sem usar uma API
  paga de terceiros.
- **KaBuM** costuma ser mais tranquilo de ler.
- Se uma loja mudar o layout da página e o scraper parar de achar o
  preço, ele já usa como fallback um regex genérico procurando
  `R$ 1.234,56` no texto da página — mas em último caso pode ser preciso
  ajustar `scraper/sources.py`.
- O parser de categorias do Promobit (`scraper/deals.py`) não depende
  de classe CSS nenhuma — ele lê o texto de todo link que aponta pra
  `/oferta/...`, que é um padrão bem estável do site. Se mesmo assim
  parar de funcionar um dia, roda o `debug_fetch.py` pra ver o que está
  vindo e ajusta o regex de preço/título se precisar.
- Isso é um scraper simples pra uso pessoal e baixo volume. Não é pensado
  pra rodar em alta frequência nem em escala — nesse ritmo (poucas
  requisições a cada 6h) o impacto nos sites é mínimo, mas vale usar com
  bom senso.
