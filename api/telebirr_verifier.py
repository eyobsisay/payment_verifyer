"""
Telebirr Payment Verification Module

This module handles fetching and parsing telebirr transaction receipts
from the Ethio Telecom API and verifying payments.
"""

import requests
from typing import Dict, Optional
from decimal import Decimal
from datetime import datetime
import re


def parse_telebirr_receipt(html_content: str) -> Dict:
    """Parse telebirr receipt HTML and extract payment information."""
    data = {}

    payer_name_pattern = r'የከፋይ ስም/Payer Name[^<]*</td>\s*<td[^>]*style="text-align: left"[^>]*>\s*([^<]+?)\s*</td>'
    payer_name_match = re.search(payer_name_pattern, html_content, re.DOTALL)
    if payer_name_match:
        data['payer_name'] = payer_name_match.group(1).strip()

    payer_telebirr_pattern = r'የከፋይ ቴሌብር ቁ\./Payer telebirr no\.[^<]*</td>\s*<td[^>]*style="text-align: left"[^>]*>\s*([^<]+?)\s*</td>'
    payer_telebirr_match = re.search(payer_telebirr_pattern, html_content, re.DOTALL)
    if payer_telebirr_match:
        data['payer_telebirr_no'] = payer_telebirr_match.group(1).strip()

    status_pattern = r'የክፍያው ሁኔታ/transaction status[^<]*<td[^>]*style="text-align: left"[^>]*>\s*([^<]+?)\s*</td>'
    status_match = re.search(status_pattern, html_content, re.DOTALL)
    if status_match:
        data['transaction_status'] = status_match.group(1).strip()

    invoice_pattern = r'<td[^>]*class="receipttableTd[^"]*"[^>]*>\s*([A-Z0-9]{8,})\s*</td>'
    invoice_match = re.search(invoice_pattern, html_content)
    if invoice_match:
        data['invoice_no'] = invoice_match.group(1).strip()

    date_pattern = r'<td[^>]*class="receipttableTd[^"]*"[^>]*>\s*(\d{2}-\d{2}-\d{4}\s+\d{2}:\d{2}:\d{2})\s*</td>'
    date_match = re.search(date_pattern, html_content)
    if date_match:
        data['payment_date'] = date_match.group(1).strip()

    settled_amount_pattern = r'<td[^>]*class="receipttableTd[^"]*"[^>]*>\s*([\d.]+)\s*Birr\s*</td>'
    settled_matches = re.findall(settled_amount_pattern, html_content)
    if settled_matches:
        try:
            data['settled_amount'] = Decimal(settled_matches[0])
        except Exception:
            data['settled_amount'] = settled_matches[0]

    total_paid_pattern = r'ጠቅላላ የተከፈለ/Total Paid Amount[^<]*</td>\s*<td[^>]*class="receipttableTd[^"]*"[^>]*>\s*([\d.]+)\s*Birr\s*</td>'
    total_paid_match = re.search(total_paid_pattern, html_content, re.DOTALL)
    if total_paid_match:
        try:
            data['total_paid'] = Decimal(total_paid_match.group(1).strip())
        except Exception:
            data['total_paid'] = total_paid_match.group(1).strip()

    reference_pattern = r'የክፍያው ማዘዣ ቁጥር/Payment reference number[^<]*<label[^>]*id="paid_reference_number"[^>]*>\s*([^<]+?)\s*</label>'
    reference_match = re.search(reference_pattern, html_content, re.DOTALL)
    if reference_match:
        ref_value = reference_match.group(1).strip()
        if ref_value:
            data['payment_reference'] = ref_value

    credited_name_patterns = [
        r'የገንዘብ ተቀባይ ስም/Credited Party name[^<]*</td>\s*<td[^>]*style="[^"]*text-align:\s*left[^"]*"[^>]*>\s*([^<]+?)\s*(?:</label>)?\s*</td>',
        r'የገንዘብ ተቀባይ ስም/Credited Party name[^<]*</td>\s*<td[^>]*>\s*([^<]+?)\s*(?:</label>)?\s*</td>',
        r'የገንዘብ ተቀባይ ስም/Credited Party name[^<]*</td>.*?<td[^>]*>\s*([^<]+?)\s*(?:</label>)?\s*</td>',
    ]
    for pattern in credited_name_patterns:
        credited_name_match = re.search(pattern, html_content, re.DOTALL | re.IGNORECASE)
        if credited_name_match:
            extracted_name = credited_name_match.group(1).strip()
            if extracted_name:
                data['credited_party_name'] = extracted_name
                break

    credited_account_pattern = r'የገንዘብ ተቀባይ ቴሌብር ቁ\./Credited party account no[^<]*</td>\s*<td[^>]*class="auto-style3"[^>]*style="text-align: left"[^>]*>\s*([^<]+?)\s*</td>'
    credited_account_match = re.search(credited_account_pattern, html_content, re.DOTALL)
    if credited_account_match:
        data['credited_party_account'] = credited_account_match.group(1).strip()

    payment_reason_pattern = r'የክፍያ ምክንያት/Payment Reason[^<]*</td>\s*<td[^>]*style="[^"]*border-bottom[^"]*"[^>]*class="auto-style18"[^>]*>\s*([^<]+?)\s*</td>'
    payment_reason_match = re.search(payment_reason_pattern, html_content, re.DOTALL)
    if payment_reason_match:
        data['payment_reason'] = payment_reason_match.group(1).strip()

    payment_channel_pattern = r'የክፍያ መንገድ/Payment channel[^<]*</td>\s*<td[^>]*class="auto-style18"[^>]*style="[^"]*border-bottom[^"]*"[^>]*>\s*([^<]+?)\s*</td>'
    payment_channel_match = re.search(payment_channel_pattern, html_content, re.DOTALL)
    if payment_channel_match:
        data['payment_channel'] = payment_channel_match.group(1).strip()

    return data


def fetch_telebirr_receipt(reference_number: str) -> Optional[str]:
    """Fetch telebirr receipt HTML from Ethio Telecom API."""
    url = f"https://transactioninfo.ethiotelecom.et/receipt/{reference_number}"
    try:
        response = requests.get(url, timeout=100)
        response.raise_for_status()
        return response.text
    except requests.exceptions.RequestException as e:
        print(f"Error fetching telebirr receipt: {e}")
        return None


def verify_telebirr_transaction(reference_number: str, expected_amount: Optional[Decimal] = None) -> Dict:
    """
    Verify a telebirr transaction by fetching and parsing the receipt.
    """
    html_content = fetch_telebirr_receipt(reference_number)
    if not html_content:
        return {'verified': False, 'error': 'Failed to fetch receipt from telebirr API', 'transaction_data': None}

    transaction_data = parse_telebirr_receipt(html_content)
    if not transaction_data:
        return {'verified': False, 'error': 'Failed to parse receipt data', 'transaction_data': None}

    status = transaction_data.get('transaction_status', '').lower()
    if status != 'completed':
        return {'verified': False, 'error': f'Transaction status is {status}, expected completed', 'transaction_data': transaction_data}

    matches = {}
    if expected_amount is not None:
        settled_amount = transaction_data.get('settled_amount')
        total_paid = transaction_data.get('total_paid')
        if settled_amount:
            try:
                settled_decimal = Decimal(str(settled_amount))
                matches['amount_match'] = settled_decimal == expected_amount
                matches['expected_amount'] = str(expected_amount)
                matches['actual_amount'] = str(settled_decimal)
            except Exception:
                matches['amount_match'] = False
                matches['error'] = 'Could not compare amounts'
        elif total_paid:
            try:
                total_decimal = Decimal(str(total_paid))
                matches['amount_match'] = total_decimal == expected_amount
                matches['expected_amount'] = str(expected_amount)
                matches['actual_amount'] = str(total_decimal)
            except Exception:
                matches['amount_match'] = False
                matches['error'] = 'Could not compare amounts'
        else:
            matches['amount_match'] = False
            matches['error'] = 'No amount found in receipt'

    return {'verified': True, 'transaction_data': transaction_data, 'matches': matches if matches else None}
