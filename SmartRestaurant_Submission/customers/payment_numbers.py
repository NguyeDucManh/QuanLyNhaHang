import uuid


def generate_payment_number():
    return 'PAY-' + uuid.uuid4().hex.upper()
