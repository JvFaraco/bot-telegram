"""Descobre ofertas em páginas de categoria do Promobit e filtra pra
mostrar só as que são "muito boas de verdade": desconto grande, preço
abaixo de um teto que você define, ou que o próprio Promobit já marcou
com a tag "Menor preço" (curadoria da equipe deles).

Não depende de classes CSS específicas — olha todos os links que apontam
pra "/oferta/..." (padrão estável do site) e faz parsing do texto de
cada card. Se o layout do site mudar bastante, pode ser preciso ajustar
o regex de preço ou a lista KNOWN_STORES abaixo.
"""
import json
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
    has_coupon = "cupom" in text.lower()

    return {
        "title": title,
        "price": new_price,
        "old_price": old_price,
        "discount_pct": discount_pct,
        "store": store,
        "is_menor_preco": is_menor_preco,
        "has_coupon": has_coupon,
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


# ---------------------------------------------------------------------------
# Extração de cupom da página da oferta
#
# Muitas ofertas do Promobit só batem o desconto anunciado usando um cupom.
# O código do cupom fica na página da oferta (/oferta/...), não na listagem.
# As funções abaixo abrem essa página e tentam achar o código, pra mandar
# junto no alerta do Telegram. É "melhor esforço": se não achar, o alerta sai
# do mesmo jeito, só sem o código.
# ---------------------------------------------------------------------------

# Palavras em maiúsculas que têm cara de cupom mas não são (evita falso
# positivo, principalmente na varredura por texto).
_COUPON_STOPWORDS = {
    "CUPOM", "COPIAR", "OFERTA", "PROMOBIT", "MENOR", "PRECO", "DESCONTO",
    "FRETE", "GRATIS", "BLACK", "FRIDAY", "AMAZON", "KABUM",
}

# Chaves de JSON (no __NEXT_DATA__ do site) que costumam guardar o cupom.
_COUPON_KEY_RE = re.compile(r"coupon|cupom|voucher|promo.?code", re.IGNORECASE)

# Um token de cupom: 4-20 caracteres, só letras maiúsculas e dígitos.
_COUPON_TOKEN_RE = re.compile(r"[A-Z0-9]{4,20}")


def _looks_like_coupon(value: str, require_digit: bool = False) -> bool:
    value = value.strip()
    if not (4 <= len(value) <= 20):
        return False
    if not re.fullmatch(r"[A-Z0-9]+", value):
        return False
    if not re.search(r"[A-Z]", value):  # precisa ter pelo menos uma letra
        return False
    if require_digit and not re.search(r"\d", value):
        return False
    return value not in _COUPON_STOPWORDS


def _extract_coupon_from_next_data(soup: BeautifulSoup) -> Optional[str]:
    """Procura o cupom no JSON embutido do site (Next.js), que é a fonte mais
    confiável quando existe."""
    tag = soup.find("script", id="__NEXT_DATA__")
    raw = tag.string if tag else None
    if not raw:
        return None
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return None

    strong: List[str] = []  # chave explicitamente sobre cupom
    weak: List[str] = []    # chave genérica "code"
    stack = [data]
    while stack:
        obj = stack.pop()
        if isinstance(obj, dict):
            for key, val in obj.items():
                if isinstance(val, str):
                    if _COUPON_KEY_RE.search(str(key)) and _looks_like_coupon(val):
                        strong.append(val.strip())
                    elif str(key).lower() == "code" and _looks_like_coupon(val, require_digit=True):
                        weak.append(val.strip())
                elif isinstance(val, (dict, list)):
                    stack.append(val)
        elif isinstance(obj, list):
            stack.extend(obj)

    if strong:
        return strong[0]
    if weak:
        return weak[0]
    return None


def _extract_coupon_from_text(soup: BeautifulSoup) -> Optional[str]:
    """Fallback: procura um código com cara de cupom perto da palavra 'cupom'
    no texto visível da página."""
    text = soup.get_text(" ", strip=True)
    low = text.lower()
    idx = low.find("cupom")
    while idx != -1:
        window = text[max(0, idx - 40): idx + 60]
        for token in _COUPON_TOKEN_RE.findall(window):
            if _looks_like_coupon(token, require_digit=True):
                return token
        idx = low.find("cupom", idx + 1)
    return None


def fetch_coupon(offer_url: str, timeout: int = 15) -> Optional[str]:
    """Abre a página de uma oferta e devolve o código do cupom, se houver.

    Melhor esforço: qualquer falha (rede, layout diferente, sem cupom) só
    devolve None — nunca levanta exceção, pra não derrubar a checagem."""
    try:
        resp = requests.get(offer_url, headers=HEADERS, timeout=timeout)
        resp.raise_for_status()
        soup = BeautifulSoup(resp.text, "html.parser")
    except Exception:  # noqa: BLE001 - cupom é opcional, não pode quebrar o alerta
        return None

    return _extract_coupon_from_next_data(soup) or _extract_coupon_from_text(soup)
