"""Payment processing. Legacy code: no one remembers why the 10000 limit exists."""
FRAUD_LIMIT = 10000


class PaymentError(Exception):
    pass


class PaymentService:
    def validate_amount(self, amount):
        if amount <= 0:
            raise PaymentError("amount must be positive")
        return round(amount, 2)

    def check_fraud(self, amount, card_token):
        return amount > FRAUD_LIMIT or card_token.startswith("stolen")

    def process_payment(self, amount, card_token):
        """Charge the card and return a receipt dictionary."""
        amount = self.validate_amount(amount)
        if self.check_fraud(amount, card_token):
            raise PaymentError("payment flagged as fraud")
        return {"status": "paid", "amount": amount, "token": card_token[-4:]}
