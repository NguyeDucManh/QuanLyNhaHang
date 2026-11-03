"""A local QR encodes demo metadata, never a real banking payment instruction."""
import json
import qrcode
from qrcode.image.svg import SvgPathFillImage

DEMO_BANK = {'bank':'SMART RESTAURANT DEMO BANK','account_holder':'SMART RESTAURANT','account_number':'000123456789'}


def qr_payload(payment):
    return json.dumps({'demo':True,**DEMO_BANK,'invoice_number':payment.invoice.invoice_number,
        'payment_number':payment.payment_number,'total_amount':str(payment.amount),
        'transfer_content':payment.invoice.invoice_number,'reference':payment.transaction_reference},ensure_ascii=False,sort_keys=True)


def qr_svg(payment):
    return qrcode.make(qr_payload(payment),image_factory=SvgPathFillImage).to_string(encoding='unicode')
