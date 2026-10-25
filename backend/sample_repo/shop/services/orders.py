from shop import db
from shop.services.payment import PaymentService


class OrderService:
    def __init__(self):
        self.payment = PaymentService()

    def cart_total(self, cart):
        return sum(item["price"] * item["qty"] for item in cart)

    def checkout(self, cart, card_token):
        total = self.cart_total(cart)
        receipt = self.payment.process_payment(total, card_token)
        order_id = db.save_order(total, receipt["status"])
        return {"order_id": order_id, "receipt": receipt}
