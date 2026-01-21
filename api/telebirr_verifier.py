"""
Telebirr Payment Verification Module

This module handles fetching and parsing telebirr transaction receipts
from the Ethio Telecom API and verifying payments.
"""

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
import urllib3
from typing import Dict, Optional
from decimal import Decimal
from datetime import datetime
import re
import time
import logging
import os

# Configure logger to write to payment.log file
logger = logging.getLogger('payment_verifyer')

# Only configure if not already configured
if not logger.handlers:
    logger.setLevel(logging.DEBUG)
    
    # Get the project root directory (payment_verifyer folder)
    # __file__ is: payment_verifyer/api/telebirr_verifier.py
    # We want: payment_verifyer/logs/payment.log
    current_file = os.path.abspath(__file__)  # Full path to telebirr_verifier.py
    api_dir = os.path.dirname(current_file)  # payment_verifyer/api
    project_root = os.path.dirname(api_dir)  # payment_verifyer (project root)
    log_dir = os.path.join(project_root, 'logs')
    
    # Create logs directory if it doesn't exist
    try:
        os.makedirs(log_dir, exist_ok=True)
    except Exception as e:
        print(f"Warning: Could not create logs directory {log_dir}: {e}")
        log_dir = current_dir  # Fallback to current directory
    
    # File handler for payment.log
    log_file = os.path.join(log_dir, 'payment.log')
    try:
        file_handler = logging.FileHandler(log_file, mode='a', encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)
        
        # Console handler (optional - for development)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        
        # Formatter
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        file_handler.setFormatter(formatter)
        console_handler.setFormatter(formatter)
        
        # Add handlers to logger
        logger.addHandler(file_handler)
        logger.addHandler(console_handler)
        
        # Prevent propagation to root logger
        logger.propagate = False
        
        # Test log to verify file creation
        logger.debug(f"Logger initialized. Log file: {log_file}")
    except Exception as e:
        print(f"Error setting up file handler for {log_file}: {e}")
        # Fallback to console only
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
        console_handler.setFormatter(formatter)
        logger.addHandler(console_handler)
        logger.warning(f"Could not create log file, using console only: {e}")


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
    
    logger.info(f"Starting fetch_telebirr_receipt for reference_number: {reference_number}")
    logger.debug(f"Target URL: {url}")
    
    # Browser-like headers - matching EXACT working browser request (Chrome on Windows)
    # Order matters - matching browser header order as closely as possible
    headers = {
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8,application/signed-exchange;v=b3;q=0.7',
        'Accept-Encoding': 'gzip, deflate, br, zstd',
        'Accept-Language': 'en-US,en;q=0.9',
        'Cache-Control': 'max-age=0',
        'Connection': 'keep-alive',
        'Cookie': '_ga=GA1.1.794892390.1768474307; _ga_FPL0B27EZN=GS2.1.s1768474306$o1$g0$t1768474310$j56$l0$h0; _ga_X7ZZ4B8L6Q=GS2.1.s1768474307$o1$g0$t1768474310$j57$l0$h297025115',
        'Host': 'transactioninfo.ethiotelecom.et',
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
    
    logger.debug(f"Request headers configured: {list(headers.keys())}")
    
    # Create a session to maintain cookies and connection
    logger.debug("Creating requests session")
    session = requests.Session()
    
    # Disable SSL verification warnings (optional, but helps with some servers)
    urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)
    
    # Configure retry strategy
    logger.debug("Configuring retry strategy: total=2, backoff_factor=0.5")
    retry_strategy = Retry(
        total=2,
        backoff_factor=0.5,
        status_forcelist=[429, 500, 502, 503, 504],
        allowed_methods=["GET"],
        connect=1,
        read=1
    )
    adapter = HTTPAdapter(max_retries=retry_strategy, pool_connections=10, pool_maxsize=10)
    session.mount("https://", adapter)
    session.mount("http://", adapter)
    logger.debug("HTTP adapter mounted to session")
    
    # Set cookies separately (requests library handles Cookie header automatically)
    cookies = {
        '_ga': 'GA1.1.794892390.1768474307',
        '_ga_FPL0B27EZN': 'GS2.1.s1768474306$o1$g0$t1768474310$j56$l0$h0',
        '_ga_X7ZZ4B8L6Q': 'GS2.1.s1768474307$o1$g0$t1768474310$j57$l0$h297025115'
    }
    logger.debug(f"Cookies configured: {list(cookies.keys())}")
    
    try:
        # First request - get the receipt and ETag
        # Don't include If-None-Match on first request
        receipt_headers = headers.copy()
        receipt_headers.pop('Cookie', None)  # Remove Cookie from headers, use cookies parameter instead
        
        logger.info(f"Making GET request to {url}")
        logger.debug(f"Request headers (without Cookie): {list(receipt_headers.keys())}")
        logger.debug(f"Request cookies: {cookies}")
        logger.debug(f"Timeout set to: 30 seconds")
        
        start_time = time.time()
        response = session.get(
            url,
            headers=receipt_headers,
            cookies=cookies,
            timeout=30,
            allow_redirects=True,
            verify=True  # SSL verification
        )
        elapsed_time = time.time() - start_time
        
        logger.info(f"Response received in {elapsed_time:.2f} seconds")
        logger.info(f"Response status code: {response.status_code}")
        logger.debug(f"Response headers: {dict(response.headers)}")
        logger.debug(f"Response URL (after redirects): {response.url}")
        logger.debug(f"Response cookies: {dict(session.cookies)}")
        
        # Handle 304 Not Modified - this means we need to make request without If-None-Match
        if response.status_code == 304:
            logger.warning("Received 304 Not Modified - retrying without If-None-Match header")
            # Remove If-None-Match and try again
            receipt_headers_no_cache = receipt_headers.copy()
            receipt_headers_no_cache.pop('If-None-Match', None)
            
            start_time = time.time()
            response = session.get(
                url,
                headers=receipt_headers_no_cache,
                cookies=session.cookies if session.cookies else cookies,
                timeout=30,
                allow_redirects=True,
                verify=True
            )
            elapsed_time = time.time() - start_time
            logger.info(f"Retry response received in {elapsed_time:.2f} seconds")
            logger.info(f"Retry response status code: {response.status_code}")
        
        response.raise_for_status()
        logger.info(f"Successfully fetched receipt HTML (length: {len(response.text)} characters)")
        return response.text
    except requests.exceptions.Timeout as e:
        error_msg = f"Connection timeout for {reference_number} - Server may be blocking requests from this IP"
        logger.error(error_msg)
        logger.error(f"Timeout exception details: {type(e).__name__}: {str(e)}")
        logger.error(f"Timeout occurred after 30 seconds - connection was not established")
        logger.debug(f"Full exception: {repr(e)}")
        print(error_msg)
        return None
    except requests.exceptions.ConnectTimeout as e:
        error_msg = f"Connection timeout (connect) for {reference_number} - Could not establish connection to server"
        logger.error(error_msg)
        logger.error(f"ConnectTimeout exception details: {type(e).__name__}: {str(e)}")
        logger.error(f"Failed to connect to {url}")
        logger.debug(f"Full exception: {repr(e)}")
        print(error_msg)
        return None
    except requests.exceptions.ReadTimeout as e:
        error_msg = f"Read timeout for {reference_number} - Server connected but did not respond in time"
        logger.error(error_msg)
        logger.error(f"ReadTimeout exception details: {type(e).__name__}: {str(e)}")
        logger.error(f"Server connected but response took longer than 30 seconds")
        logger.debug(f"Full exception: {repr(e)}")
        print(error_msg)
        return None
    except requests.exceptions.ConnectionError as e:
        error_msg = f"Connection error for {reference_number}: {e} - Server may be blocking requests from this IP"
        logger.error(error_msg)
        logger.error(f"ConnectionError exception details: {type(e).__name__}: {str(e)}")
        logger.error(f"Failed to establish connection to {url}")
        logger.debug(f"Full exception: {repr(e)}")
        if hasattr(e, 'request'):
            logger.debug(f"Failed request URL: {e.request.url if e.request else 'N/A'}")
        print(error_msg)
        return None
    except requests.exceptions.SSLError as e:
        error_msg = f"SSL error for {reference_number}: {e}"
        logger.error(error_msg)
        logger.error(f"SSLError exception details: {type(e).__name__}: {str(e)}")
        logger.debug(f"Full exception: {repr(e)}")
        print(error_msg)
        return None
    except requests.exceptions.RequestException as e:
        error_msg = f"Request error for {reference_number}: {e}"
        logger.error(error_msg)
        logger.error(f"RequestException type: {type(e).__name__}")
        logger.error(f"RequestException details: {str(e)}")
        logger.debug(f"Full exception: {repr(e)}")
        if hasattr(e, 'response') and e.response is not None:
            logger.error(f"Response status code: {e.response.status_code}")
            logger.error(f"Response headers: {dict(e.response.headers)}")
        print(error_msg)
        return None
    except Exception as e:
        error_msg = f"Unexpected error for {reference_number}: {e}"
        logger.error(error_msg)
        logger.error(f"Unexpected exception type: {type(e).__name__}")
        logger.error(f"Unexpected exception details: {str(e)}")
        logger.debug(f"Full exception: {repr(e)}", exc_info=True)
        print(error_msg)
        return None
    finally:
        logger.debug("Closing session")
        session.close()
        logger.info(f"Completed fetch_telebirr_receipt for reference_number: {reference_number}")


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
