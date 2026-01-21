"""
Telebirr Payment Verification Module

This module handles fetching and parsing telebirr transaction receipts
from the Ethio Telecom API and verifying payments.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from typing import Dict, Optional
from decimal import Decimal
from datetime import datetime
import re
import time
import logging


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
    
    # Browser-like headers - matching exact working browser request (Chrome on Windows)
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Sec-CH-UA': '"Google Chrome";v="143", "Chromium";v="143", "Not A(Brand";v="24"',
        'Sec-CH-UA-Mobile': '?0',
        'Sec-CH-UA-Platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'none',
        'Sec-Fetch-User': '?1',
        'Upgrade-Insecure-Requests': '1',
        'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
    }
    
    # Create a session to maintain cookies
    session = requests.Session()
    
    # Configure retry strategy - but don't retry on timeout, just fail fast
    retry_strategy = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        connect=1,  # Only retry connection errors once
        read=1
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    
    # Set cookies that might be needed (from browser request)
    cookies = {
        '_ga': 'GA1.1.794892390.1768474307',
        '_ga_FPL0B27EZN': 'GS2.1.s1768474306$o1$g0$t1768474310$j56$l0$h0',
        '_ga_X7ZZ4B8L6Q': 'GS2.1.s1768474307$o1$g0$t1768474310$j57$l0$h297025115'
    }
    
    try:
        # First, visit the main page to establish session and get any required cookies
        # This mimics browser behavior - visiting homepage first
        try:
            main_page_headers = headers.copy()
            main_response = session.get(
                'https://transactioninfo.ethiotelecom.et/',
                headers=main_page_headers,
                cookies=cookies,
                timeout=15,
                allow_redirects=True
            )
            # Update cookies from response if any new ones are set
            session.cookies.update(main_response.cookies)
            # Store ETag if provided for future requests
            etag = main_response.headers.get('ETag')
        except Exception as e:
            logger.warning(f"Could not establish session on main page: {e}")
            etag = None
        
        # Small delay to mimic human behavior
        time.sleep(0.5)
        
        # Now fetch the receipt with session cookies
        receipt_headers = headers.copy()
        # Add If-None-Match header if we have an ETag from previous request
        if etag:
            receipt_headers['If-None-Match'] = etag
        
        response = session.get(
            url,
            headers=receipt_headers,
            cookies=session.cookies if session.cookies else cookies,
            timeout=20,
            allow_redirects=True
        )
        
        # Handle 304 Not Modified response (cached content)
        if response.status_code == 304:
            # For 304, we need to use cached content or make another request without If-None-Match
            receipt_headers_no_cache = receipt_headers.copy()
            receipt_headers_no_cache.pop('If-None-Match', None)
            response = session.get(
                url,
                headers=receipt_headers_no_cache,
                cookies=session.cookies if session.cookies else cookies,
                timeout=20,
                allow_redirects=True
            )
        
        response.raise_for_status()
        return response.text
    except requests.exceptions.Timeout:
        error_msg = f"Connection timeout for {reference_number} - Server may be blocking requests from this IP"
        logger.error(error_msg)
        print(error_msg)
        return None
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Connection error for {reference_number}: {e} - Server may be blocking requests from this IP"
        logger.error(error_msg)
        print(error_msg)
        return None
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error for {reference_number}: {e}"
        logger.error(error_msg)
        print(error_msg)
        return None
    finally:
        session.close()


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
