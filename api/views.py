from decimal import Decimal, InvalidOperation

from drf_yasg import openapi
from drf_yasg.utils import swagger_auto_schema
from rest_framework import status
from rest_framework.decorators import api_view, permission_classes
from rest_framework.permissions import AllowAny
from rest_framework.response import Response

from .sdk import PaymentVerificationSDK
from .telebirr_verifier import fetch_telebirr_receipt


def _make_serializable(value):
    """Convert Decimals and nested structures into JSON-safe types."""
    if isinstance(value, Decimal):
        return str(value)
    if isinstance(value, dict):
        return {k: _make_serializable(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_make_serializable(v) for v in value]
    return value


@swagger_auto_schema(
    method='post',
    operation_description='Verify a Telebirr payment transaction by reference number.',
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['reference_number'],
        properties={
            'reference_number': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Transaction reference number from Telebirr (e.g., CLS5C9Y98X)',
                example='CLS5C9Y98X'
            ),
            'expected_amount': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Optional expected payment amount to verify against',
                example='100.00'
            ),
        }
    ),
    responses={
        200: openapi.Response(
            description='Payment verified successfully',
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'verified': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True),
                    'transaction_data': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        description='Transaction details from receipt'
                    ),
                    'verified_amount': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='Amount from receipt',
                        example='100.00'
                    ),
                    'message': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        example='Transaction verified successfully'
                    ),
                }
            )
        ),
        400: openapi.Response(
            description='Verification failed or invalid request',
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'verified': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                    'error': openapi.Schema(type=openapi.TYPE_STRING),
                    'transaction_data': openapi.Schema(type=openapi.TYPE_OBJECT),
                }
            )
        ),
    },
    tags=['Payment Verification']
)
@api_view(['POST'])
@permission_classes([AllowAny])
def verify_telebirr_payment(request):
    """POST endpoint to verify a Telebirr payment by reference number."""
    reference_number = request.data.get('reference_number')
    if not reference_number:
        return Response({'error': 'reference_number is required'}, status=status.HTTP_400_BAD_REQUEST)

    expected_amount = None
    if 'expected_amount' in request.data:
        try:
            expected_amount = Decimal(str(request.data['expected_amount']))
        except (InvalidOperation, ValueError):
            return Response({'error': 'Invalid expected_amount format'}, status=status.HTTP_400_BAD_REQUEST)

    result = PaymentVerificationSDK.verify_telebirr_payment(
        reference_number=reference_number,
        expected_amount=expected_amount
    )
    status_code = status.HTTP_200_OK if result.get('verified') else status.HTTP_400_BAD_REQUEST
    return Response(_make_serializable(result), status=status_code)


@swagger_auto_schema(
    method='get',
    operation_description='Verify a Telebirr payment by reference number using GET request.',
    manual_parameters=[
        openapi.Parameter(
            'reference_number',
            openapi.IN_PATH,
            description='Transaction reference number from Telebirr (e.g., CLS5C9Y98X)',
            type=openapi.TYPE_STRING,
            required=True,
            example='CLS5C9Y98X'
        ),
        openapi.Parameter(
            'expected_amount',
            openapi.IN_QUERY,
            description='Optional expected payment amount to verify against',
            type=openapi.TYPE_STRING,
            required=False,
            example='100.00'
        ),
    ],
    responses={
        200: openapi.Response(
            description='Payment verified successfully',
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'verified': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=True),
                    'transaction_data': openapi.Schema(
                        type=openapi.TYPE_OBJECT,
                        description='Transaction details from receipt'
                    ),
                    'verified_amount': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='Amount from receipt',
                        example='100.00'
                    ),
                    'message': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        example='Transaction verified successfully'
                    ),
                }
            )
        ),
        400: openapi.Response(
            description='Verification failed or invalid request',
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'verified': openapi.Schema(type=openapi.TYPE_BOOLEAN, example=False),
                    'error': openapi.Schema(type=openapi.TYPE_STRING),
                    'transaction_data': openapi.Schema(type=openapi.TYPE_OBJECT),
                }
            )
        ),
    },
    tags=['Payment Verification']
)
@api_view(['GET'])
@permission_classes([AllowAny])
def verify_telebirr_payment_by_reference(request, reference_number):
    """GET endpoint to verify a Telebirr payment by reference number."""
    expected_amount = None
    if 'expected_amount' in request.query_params:
        try:
            expected_amount = Decimal(str(request.query_params['expected_amount']))
        except (InvalidOperation, ValueError):
            return Response({'error': 'Invalid expected_amount format'}, status=status.HTTP_400_BAD_REQUEST)

    result = PaymentVerificationSDK.verify_telebirr_payment(
        reference_number=reference_number,
        expected_amount=expected_amount
    )
    status_code = status.HTTP_200_OK if result.get('verified') else status.HTTP_400_BAD_REQUEST
    return Response(_make_serializable(result), status=status_code)


@swagger_auto_schema(
    method='post',
    operation_description='Fetch raw HTML receipt from Telebirr API without parsing.',
    request_body=openapi.Schema(
        type=openapi.TYPE_OBJECT,
        required=['reference_number'],
        properties={
            'reference_number': openapi.Schema(
                type=openapi.TYPE_STRING,
                description='Transaction reference number from Telebirr (e.g., CLS5C9Y98X)',
                example='CLS5C9Y98X'
            ),
        }
    ),
    responses={
        200: openapi.Response(
            description='Raw HTML receipt fetched successfully',
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'html': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='Raw HTML content from Telebirr receipt'
                    ),
                    'reference_number': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='Reference number used for the request'
                    ),
                }
            )
        ),
        400: openapi.Response(
            description='Failed to fetch receipt',
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'error': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )
        ),
    },
    tags=['Payment Verification']
)
@api_view(['POST'])
@permission_classes([AllowAny])
def fetch_telebirr_receipt_html(request):
    """POST endpoint to fetch raw HTML receipt from Telebirr API."""
    reference_number = request.data.get('reference_number')
    if not reference_number:
        return Response({'error': 'reference_number is required'}, status=status.HTTP_400_BAD_REQUEST)
    
    html_content = fetch_telebirr_receipt(reference_number)
    if not html_content:
        return Response(
            {'error': 'Failed to fetch receipt from telebirr API', 'reference_number': reference_number},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    return Response({
        'html': html_content,
        'reference_number': reference_number
    }, status=status.HTTP_200_OK)


@swagger_auto_schema(
    method='get',
    operation_description='Fetch raw HTML receipt from Telebirr API without parsing using GET request.',
    manual_parameters=[
        openapi.Parameter(
            'reference_number',
            openapi.IN_PATH,
            description='Transaction reference number from Telebirr (e.g., CLS5C9Y98X)',
            type=openapi.TYPE_STRING,
            required=True,
            example='CLS5C9Y98X'
        ),
    ],
    responses={
        200: openapi.Response(
            description='Raw HTML receipt fetched successfully',
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'html': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='Raw HTML content from Telebirr receipt'
                    ),
                    'reference_number': openapi.Schema(
                        type=openapi.TYPE_STRING,
                        description='Reference number used for the request'
                    ),
                }
            )
        ),
        400: openapi.Response(
            description='Failed to fetch receipt',
            schema=openapi.Schema(
                type=openapi.TYPE_OBJECT,
                properties={
                    'error': openapi.Schema(type=openapi.TYPE_STRING),
                }
            )
        ),
    },
    tags=['Payment Verification']
)
@api_view(['GET'])
@permission_classes([AllowAny])
def fetch_telebirr_receipt_html_by_reference(request, reference_number):
    """GET endpoint to fetch raw HTML receipt from Telebirr API."""
    html_content = fetch_telebirr_receipt(reference_number)
    if not html_content:
        return Response(
            {'error': 'Failed to fetch receipt from telebirr API', 'reference_number': reference_number},
            status=status.HTTP_400_BAD_REQUEST
        )
    
    return Response({
        'html': html_content,
        'reference_number': reference_number
    }, status=status.HTTP_200_OK)
