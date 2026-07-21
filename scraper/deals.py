"""Descobre ofertas em páginas de categoria do Promobit e filtra pra
mostrar só as que são "muito boas de verdade": desconto grande, preço
abaixo de um teto que você define, ou que o próprio Promobit já marcou
com a tag "Menor preço" (curadoria da equipe deles).

Não depende de classes CSS específicas — olha todos os links que apontam
pra "/oferta/..." (padrão estável do site) e faz parsing do texto de
cada card. Se o layout do site mudar bastante, pode ser preciso ajustar
o regex de preço ou a lista KNOWN_STORES abaixo.
"""
import re
from typing import Dict, List, Optional

import requests
from bs4 import BeautifulSoup

from .sources import HEADERS

KNOWN_STORES = [
    "KaBuM!", "Amazon", "Mercado Livre", "Magazine Luiza", "Casas Bahia",
    "Shopee", "Fast Shop", "Pichau", "Americanas", "Submarino", "Shoptime",
    "Ponto", "Extra", "Carrefour", "AliExpress", "Centauro",
]

PRICE_RE = re.compile(r"R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})")


def _parse_price(raw: str) -> float:
    return float(raw.replace(".", "").replace(",", "."))


def _parse_deal_card(anchor) -> Optional[Dict]:
    href = anchor.get("href", "")
    if "/oferta/" not in href:
        return None

    text = anchor.get_text(" ", strip=True)
    prices = [_parse_price(m) for m in PRICE_RE.findall(text)]
    if not prices:
        return None

    # Convenção observada: "R$ {preço antigo} R$ {preço atual}" quando tem
    # desconto visível, ou só um preço quando não tem. O preço atual é
    # sempre o último valor no texto do card.
    new_price = prices[-1]
    old_price = prices[0] if len(prices) > 1 else None
    discount_pct = None
    if old_price and old_price > new_price:
        discount_pct = round((old_price - new_price) / old_price * 100, 1)

    title = re.split(r"R\$", text, maxsplit=1)[0]
    title = title.replace("Imagem da oferta", "").replace("Menor preço", "").strip()

    store = next((s for s in KNOWN_STORES if s.lower() in text.lower()), None)
    is_menor_preco = "menor preço" in text.lower()

    return {
        "title": title,
        "price": new_price,
        "old_price": old_price,
        "discount_pct": discount_pct,
        "store": store,
        "is_menor_preco": is_menor_preco,
        "url": href if href.startswith("http") else f"https://www.promobit.com.br{href}",
    }


def fetch_deals(category_url: str, timeout: int = 20) -> List[Dict]:
    """Busca uma página de categoria e retorna a lista de ofertas achadas."""
    resp = requests.get(category_url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    deals: List[Dict] = []
    seen_urls = set()
    for anchor in soup.find_all("a", href=True):
        deal = _parse_deal_card(anchor)
        if deal and deal["url"] not in seen_urls:
            seen_urls.add(deal["url"])
            deals.append(deal)
    return deals


def is_good_deal(deal: Dict, watch: Dict) -> bool:
    """Aplica os filtros de um watch. O desconto é o critério decisivo:
    quando 'min_discount_pct' está definido, a oferta SÓ passa se tiver um
    desconto visível e igual/maior que esse valor — nada de passar só por
    preço abaixo do teto ou pela tag 'Menor preço'. Assim só chega o que é
    realmente um descontão."""
    title_lower = deal["title"].lower()

    keywords_all = [k.lower() for k in watch.get("keywords_all", [])]
    if not all(k in title_lower for k in keywords_all):
        return False

    keywords_any = [k.lower() for k in watch.get("keywords_any", [])]
    if keywords_any and not any(k in title_lower for k in keywords_any):
        return False

    # Teto de preço é um limite rígido (opcional): acima disso, descarta.
    max_price = watch.get("max_price")
    if max_price is not None and deal["price"] > max_price:
        return False

    # Desconto é o critério que manda. Se o watch define min_discount_pct, a
    # oferta precisa ter desconto visível e >= esse valor. Sem atalho: preço
    # baixo ou "Menor preço" sozinhos não bastam.
    min_discount = watch.get("min_discount_pct")
    if min_discount is not None:
        return (
            deal["discount_pct"] is not None
            and deal["discount_pct"] >= min_discount
        )

    # Watch sem min_discount_pct definido: modo permissivo (preço abaixo do
    # teto ou marcado como "Menor preço" pela curadoria do Promobit).
    good_price = max_price is not None and deal["price"] <= max_price
    return good_price or deal["is_menor_preco"]
