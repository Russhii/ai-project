from shop import db
from shop.services import OrderService
from shop.web import router

order_service = OrderService()


@router.post("/checkout")
def checkout_controller(cart, card_token):
    return order_service.checkout(cart, card_token)


@router.get("/orders/{order_id}")
def get_order_controller(order_id):
    return db.find_order(order_id)
