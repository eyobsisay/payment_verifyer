"""
Payment Verification SDK

Provides a unified interface for verifying payments.
"""

from decimal import Decimal, InvalidOperation
from typing import Dict, Optional

from .telebirr_verifier import verify_telebirr_transaction


class PaymentVerificationSDK:
    """SDK for payment verification across different payment methods."""

    @staticmethod
    def verify_telebirr_payment(
        reference_number: str,
        expected_amount: Optional[Decimal] = None
    ) -> Dict:
        verification_result = verify_telebirr_transaction(reference_number, expected_amount)

        if not verification_result.get('verified'):
            return {
                'verified': False,
                'error': verification_result.get('error', 'Verification failed'),
                'transaction_data': verification_result.get('transaction_data', {}),
                'verified_amount': None,
                'amount_verification': None
            }

        transaction_data = verification_result['transaction_data']
        settled_amount = transaction_data.get('settled_amount') or transaction_data.get('total_paid')
        verified_amount = None
        if settled_amount:
            try:
                verified_amount = Decimal(str(settled_amount))
            except (InvalidOperation, ValueError):
                pass

        response = {
            'verified': True,
            'transaction_data': transaction_data,
            'verified_amount': verified_amount,
            'message': 'Transaction verified successfully'
        }

        if expected_amount is not None and verified_amount is not None:
            amount_diff = abs(verified_amount - expected_amount)
            amount_match = amount_diff < Decimal('0.01')
            response['amount_verification'] = {
                'amount_match': amount_match,
                'expected_amount': str(expected_amount),
                'actual_amount': str(verified_amount),
                'difference': str(amount_diff)
            }
            if not amount_match:
                response['error'] = f'Amount mismatch: Expected {expected_amount} ETB, but receipt shows {verified_amount} ETB'
        elif expected_amount is not None and verified_amount is None:
            response['error'] = 'No amount found in verification data. Cannot verify payment amount.'
            response['message'] = 'Transaction verified but amount could not be confirmed'
            response['amount_verification'] = {
                'amount_match': False,
                'expected_amount': str(expected_amount),
                'actual_amount': None,
                'difference': None
            }

        return response

    @staticmethod
    def verify_payment(
        payment_method_code: str,
        reference_number: str,
        expected_amount: Optional[Decimal] = None
    ) -> Dict:
        method = payment_method_code.lower()
        if 'telebirr' in method or 'tele' in method:
            return PaymentVerificationSDK.verify_telebirr_payment(reference_number, expected_amount)
        return {
            'verified': False,
            'error': f'Payment method "{payment_method_code}" is not supported for verification',
            'transaction_data': {},
            'verified_amount': None,
            'amount_verification': None
        }
