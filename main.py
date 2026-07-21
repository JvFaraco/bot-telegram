"""Checa os preços/ofertas configurados em config.json e manda alerta no
Telegram quando algo vale muito a pena.

Dois tipos de vigia, configurados em config.json:

- "product_watches": acompanha uma página de produto específica (ex: o
  Vivobook Go 15 na Amazon) e avisa quando o preço cai abaixo de um teto.
- "deal_watches": vasculha uma categoria inteira do Promobit (ex:
  "notebooks", "smartwatch") e avisa só das ofertas que batem as
  palavras-chave e são "muito boas de verdade" (desconto grande, preço
  abaixo de um teto, ou já marcadas como "Menor preço" pela curadoria do
  Promobit).

Feito para rodar periodicamente via GitHub Actions. A memória de "já
avisei sobre isso" fica em state.json, que o workflow commita de volta
no repositório a cada execução.
"""
import json
from pathlib import Path

from scraper.deals import fetch_deals, is_good_deal
from scraper.sources import get_price
from scraper.telegram import notify

BASE_DIR = Path(__file__).parent
CONFIG_PATH = BASE_DIR / "config.json"
STATE_PATH = BASE_DIR / "state.json"


def load_json(path: Path, default):
    if path.exists():
        return json.loads(path.read_text(encoding="utf-8"))
    return default


def save_json(path: Path, data) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def check_product(item: dict, state: dict) -> None:
    name = item["name"]
    url = item["url"]
    threshold = item["price_threshold"]

    try:
        price = get_price(url)
    except Exception as exc:  # noqa: BLE001 - segue pros próximos itens mesmo se um falhar
        print(f"[warn] falha ao buscar preço de '{name}': {exc}")
        return

    if price is None:
        print(f"[warn] não encontrei preço na página de '{name}' (layout pode ter mudado)")
        return

    print(f"[produto] {name}: R$ {price:.2f} (limite R$ {threshold:.2f})")

    products_state = state.setdefault("products", {})
    entry = products_state.setdefault(url, {})
    last_alerted = entry.get("last_alerted_price")

    if price <= threshold and price != last_alerted:
        notify(
            f"🔥 <b>{name}</b>\n"
            f"R$ {price:.2f} (abaixo do limite de R$ {threshold:.2f})\n"
            f"{url}"
        )
        entry["last_alerted_price"] = price

    entry["last_seen_price"] = price


def check_deal_watch(watch: dict, state: dict) -> None:
    name = watch["name"]
    url = watch["url"]

    try:
        deals = fetch_deals(url)
    except Exception as exc:  # noqa: BLE001
        print(f"[warn] falha ao buscar ofertas de '{name}': {exc}")
        return

    print(f"[categoria] {name}: {len(deals)} ofertas encontradas na página")

    alerted_urls = state.setdefault("deals_alerted", [])

    for deal in deals:
        if not is_good_deal(deal, watch):
            continue
        if deal["url"] in alerted_urls:
            continue

        discount_txt = f" ({deal['discount_pct']:.0f}% off)" if deal["discount_pct"] else ""
        curated_txt = " ⭐ Menor preço" if deal["is_menor_preco"] else ""
        store_txt = f" — {deal['store']}" if deal["store"] else ""

        notify(
            f"🔥 <b>[{name}]</b> {deal['title']}\n"
            f"R$ {deal['price']:.2f}{discount_txt}{curated_txt}{store_txt}\n"
            f"{deal['url']}"
        )
        alerted_urls.append(deal["url"])

    # não deixa a lista crescer pra sempre
    state["deals_alerted"] = alerted_urls[-500:]


def main() -> None:
    config = load_json(CONFIG_PATH, {"product_watches": [], "deal_watches": []})
    state = load_json(STATE_PATH, {})

    for item in config.get("product_watches", []):
        check_product(item, state)

    for watch in config.get("deal_watches", []):
        check_deal_watch(watch, state)

    save_json(STATE_PATH, state)


if __name__ == "__main__":
    main()
