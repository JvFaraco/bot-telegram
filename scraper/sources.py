"""Extração de preço de páginas de produto.

Estratégia: primeiro tenta ler o bloco JSON-LD (schema.org Product/Offer)
que a maioria dos e-commerces embute para SEO — isso é muito mais estável
que depender de classes CSS, que mudam com frequência. Se não encontrar,
cai para um regex simples procurando o primeiro "R$ 1.234,56" na página.
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
    match = re.search(r"R\$\s?(\d{1,3}(?:\.\d{3})*,\d{2})", text)
    if not match:
        return None
    value = match.group(1).replace(".", "").replace(",", ".")
    return float(value)


def get_price(url: str, timeout: int = 20):
    """Busca a página e tenta extrair o preço atual em BRL. Retorna None
    se não conseguir (página bloqueou o robô, mudou de layout, etc.)."""
    resp = requests.get(url, headers=HEADERS, timeout=timeout)
    resp.raise_for_status()
    soup = BeautifulSoup(resp.text, "html.parser")
    return _price_from_jsonld(soup) or _price_from_text(soup)
