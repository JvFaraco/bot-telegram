"""Extração de preço de páginas de produto.

Ordem de tentativa:
1. Blocos específicos da Amazon (buy box). A página da Amazon tem MUITO
   preço solto (parcelas, acessórios, patrocinados, "comprados juntos"),
   então pegar "o primeiro R$ da página" erra feio — foi o que fez um
   notebook aparecer como "R$ 148,00". Aqui a gente mira o bloco de preço
   principal.
2. JSON-LD (schema.org Product/Offer) que a maioria dos e-commerces embute
   pra SEO — estável e independente de classe CSS. Boa fonte pra KaBuM.
3. Último caso: regex procurando "R$ 1.234,56" no texto da página.
"""
import json
import re

import requests
from bs4 import BeautifulSoup

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
        "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept-Language": "pt-BR,pt;q=0.9",
}

# Um valor em reais, com separador de milhar ("2.799,00") ou sem ("2799,00").
_BRL_NUM = r"\d{1,3}(?:\.\d{3})+,\d{2}|\d+,\d{2}"
_BRL_NUM_RE = re.compile(_BRL_NUM)


def _to_float(raw: str) -> float:
    return float(raw.replace(".", "").replace(",", "."))


def _first_brl(text: str):
    match = _BRL_NUM_RE.search(text or "")
    return _to_float(match.group(0)) if match else None


# Blocos onde a Amazon coloca o preço principal (buy box), em ordem de
# preferência. Layouts variam, então tentamos vários.
_AMAZON_PRICE_CONTAINERS = (
    "corePriceDisplay_desktop_feature_div",
    "corePrice_feature_div",
    "apex_desktop",
    "buybox",
)


def _price_from_amazon(soup: BeautifulSoup):
    """Preço da buy box da Amazon. Ignora o preço 'de' riscado e os preços
    de acessórios/parcelas espalhados pela página."""
    for container_id in _AMAZON_PRICE_CONTAINERS:
        container = soup.find(id=container_id)
        if container is None:
            continue

        # A Amazon repete o preço num <span class="a-offscreen"> (texto pra
        # leitor de tela), que é a fonte mais limpa. Pegamos o que está num
        # a-price NÃO riscado (o riscado é o a-text-price, preço antigo).
        for off in container.select("span.a-price:not(.a-text-price) span.a-offscreen"):
            price = _first_brl(off.get_text(" ", strip=True))
            if price is not None:
                return price

        # Fallback dentro do bloco: parte inteira + centavos separados.
        whole = container.select_one("span.a-price-whole")
        if whole is not None:
            frac = container.select_one("span.a-price-fraction")
            cents = frac.get_text(strip=True) if frac is not None else "00"
            price = _first_brl(whole.get_text(strip=True).rstrip(".,") + "," + cents)
            if price is not None:
                return price

    # Layouts antigos da Amazon.
    for old_id in ("priceblock_ourprice", "priceblock_dealprice", "priceblock_saleprice"):
        el = soup.find(id=old_id)
        if el is not None:
            price = _first_brl(el.get_text(" ", strip=True))
            if price is not None:
                return price

    return None


def _price_from_jsonld(soup: BeautifulSoup):
    for tag in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(tag.string)
        except (TypeError, ValueError):
            continue
        candidates = data if isinstance(data, list) else [data]
        for item in candidates:
            if not isinstance(item, dict):
                continue
            offers = item.get("offers")
            if not offers:
                continue
            offers_list = offers if isinstance(offers, list) else [offers]
            for offer in offers_list:
                if not isinstance(offer, dict):
                    continue
                price = offer.get("price") or offer.get("lowPrice")
                if price:
                    try:
                        return float(price)
                    except (TypeError, ValueError):
                        continue
    return None


def _price_from_text(soup: BeautifulSoup):
    text = soup.get_text(" ", strip=True)
    match = re.search(r"R\$\s?(" + _BRL_NUM + r")", text)
    return _to_float(match.group(1)) if match else None


def get_price(url: str, timeout: int = 20):
    """Busca a página e tenta extrair o preço atual em BRL. Retorna None
    se não conseguir (página bloqueou o robô, mudou de layout, etc.)."""
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")

    price = None
    if "amazon." in url:
        price = _price_from_amazon(soup)
    if price is None:
        price = _price_from_jsonld(soup)
    if price is None:
        price = _price_from_text(soup)
    return price
