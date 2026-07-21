"""Ferramenta de debug: mostra o cupom que o bot consegue extrair de uma
página de oferta do Promobit, sem mandar nada pro Telegram. Útil pra
conferir se a extração de cupom está funcionando numa oferta específica.

Uso:
    python debug_coupon.py https://www.promobit.com.br/oferta/....
"""
import sys

from scraper.deals import fetch_coupon


def main() -> None:
    if len(sys.argv) < 2:
        print("Uso: python debug_coupon.py <url_da_oferta>")
        raise SystemExit(1)

    url = sys.argv[1]
    coupon = fetch_coupon(url)
    if coupon:
        print(f"Cupom encontrado: {coupon}")
    else:
        print("Nenhum cupom encontrado nessa oferta "
              "(pode não ter cupom, ou o layout mudou).")


if __name__ == "__main__":
    main()
