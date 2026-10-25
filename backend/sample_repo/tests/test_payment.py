import pytest

from shop.services.payment import PaymentError, PaymentService


def test_process_payment_returns_receipt():
    receipt = PaymentService().process_payment(25.456, "tok_12345678")
    assert receipt == {"status": "paid", "amount": 25.46, "token": "5678"}


def test_process_payment_rejects_fraud():
    with pytest.raises(PaymentError):
        PaymentService().process_payment(20000, "tok_1")
