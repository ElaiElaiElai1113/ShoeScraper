from sneakers.parsers import (
    extract_candidates_from_html,
    extract_marketplace_candidates,
    page_requires_login,
)


def test_generic_parser_extracts_retail_product_details():
    html = """
    <article>
      <a href="/product/iq9773-400">Ja Morant Air Force 1 Denim IQ9773-400</a>
      <span>$170.00</span>
      <button>Add to cart</button>
    </article>
    """

    products = extract_candidates_from_html("https://example.test/search", html, "nike_au")

    assert products[0].title == "Ja Morant Air Force 1 Denim IQ9773-400"
    assert products[0].url == "https://example.test/product/iq9773-400"
    assert products[0].current_price == 170.0
    assert products[0].availability == "available"
    assert products[0].source_type == "retail"


def test_marketplace_parser_extracts_listing_details():
    html = """
    <li class="s-item">
      <a href="https://www.ebay.com.au/itm/123">Jordan 9 Retro Wheat AR4491-700 US10</a>
      <span class="s-item__price">AU $120.00</span>
      <span class="s-item__location">Sydney, NSW</span>
      <img src="https://img.example/jordan.jpg">
    </li>
    """

    products = extract_marketplace_candidates("https://www.ebay.com.au/sch/i.html", html, "ebay_au")

    assert products[0].title == "Jordan 9 Retro Wheat AR4491-700 US10"
    assert products[0].current_price == 120.0
    assert products[0].location == "Sydney, NSW"
    assert products[0].image_url == "https://img.example/jordan.jpg"
    assert products[0].condition_type == "second_hand"


def test_facebook_login_gate_is_detected():
    html = "<html><title>Facebook</title><body>Log in to Facebook to continue to Marketplace</body></html>"

    assert page_requires_login(html) is True
