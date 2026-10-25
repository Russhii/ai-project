from shop.services.orders import OrderService


def test_cart_total():
    assert OrderService().cart_total([{"price": 2.5, "qty": 2}]) == 5.0
