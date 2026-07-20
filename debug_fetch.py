"""Ferramenta de debug: mostra o que o parser está achando numa categoria
do Promobit, sem mandar nada pro Telegram. Útil pra conferir se o
scraping ainda está funcionando ou se precisa de ajuste.

Uso:
    python debug_fetch.py https://www.promobit.com.br/promocoes/notebooks/s/
"""
import sys

from scraper.deals import fetch_deals


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python debug_fetch.py <url_da_categoria>")
        raise SystemExit(1)

    url = sys.argv[1]
    deals = fetch_deals(url)

    print(f"{len(deals)} ofertas encontradas em {url}\n")
    for deal in deals:
        discount = f"{deal['discount_pct']:.0f}% off" if deal["discount_pct"] else "sem desconto visível"
        curated = " ⭐ Menor preço" if deal["is_menor_preco"] else ""
        print(f"- {deal['title'][:70]}")
        print(f"  R$ {deal['price']:.2f} ({discount}){curated} — {deal['store'] or '?'}")
        print(f"  {deal['url']}\n")


if __name__ == "__main__":
    main()
