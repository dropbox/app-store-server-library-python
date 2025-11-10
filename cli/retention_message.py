#!/usr/bin/env python3
# Copyright (c) 2023 Apple Inc. Licensed under MIT License.

"""
CLI tool for managing retention messages via the App Store Server API.

This tool allows you to upload, list, and delete retention messages that can be
displayed to users to encourage app re-engagement.

Example usage:
    # Upload a message with auto-generated ID
    python retention_message.py --key-id KEY123 --issuer-id ISS456 \\
        --bundle-id com.example.app --p8-file key.p8 \\
        --header "Welcome back!" --body "Check out our new features"

    # List all messages
    python retention_message.py --key-id KEY123 --issuer-id ISS456 \\
        --bundle-id com.example.app --p8-file key.p8 --action list

    # Delete a message
    python retention_message.py --key-id KEY123 --issuer-id ISS456 \\
        --bundle-id com.example.app --p8-file key.p8 \\
        --action delete --message-id abc-123-def
"""

import argparse
import csv
import json
import os
import signal
import sys
import time
import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional, Dict, List, Tuple, Any

# Add parent directory to path to import the library
sys.path.insert(0, str(Path(__file__).parent.parent))

from appstoreserverlibrary.api_client import AppStoreServerAPIClient, APIException, APIError
from appstoreserverlibrary.models.Environment import Environment
from appstoreserverlibrary.models.UploadMessageRequestBody import UploadMessageRequestBody
from appstoreserverlibrary.models.UploadMessageImage import UploadMessageImage
from appstoreserverlibrary.models.DefaultConfigurationRequest import DefaultConfigurationRequest


def load_private_key(p8_file_path: str) -> bytes:
    """Load private key from .p8 file."""
    try:
        with open(p8_file_path, 'rb') as f:
            return f.read()
    except FileNotFoundError:
        print(f"Error: Private key file not found: {p8_file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading private key file: {e}")
        sys.exit(1)


def create_api_client(args) -> AppStoreServerAPIClient:
    """Create and return an API client with the provided credentials."""
    private_key = load_private_key(args.p8_file)

    environment = Environment.SANDBOX if args.environment == 'SANDBOX' else Environment.PRODUCTION

    return AppStoreServerAPIClient(
        signing_key=private_key,
        key_id=args.key_id,
        issuer_id=args.issuer_id,
        bundle_id=args.bundle_id,
        environment=environment
    )


class InterruptHandler:
    """Handle graceful interrupts (Ctrl+C) during bulk operations."""

    def __init__(self):
        self.interrupted = False
        self.original_handler = None

    def __enter__(self):
        """Set up the interrupt handler."""
        self.interrupted = False
        self.original_handler = signal.signal(signal.SIGINT, self._handler)
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        """Restore the original interrupt handler."""
        signal.signal(signal.SIGINT, self.original_handler)
        return False  # Don't suppress exceptions

    def _handler(self, signum, frame):
        """Handle the interrupt signal."""
        if not self.interrupted:
            print("\n\n⚠ Interrupt received! Finishing current operation and stopping gracefully...")
            print("(Press Ctrl+C again to force quit)")
            self.interrupted = True
        else:
            # Second interrupt - let it through
            signal.signal(signal.SIGINT, self.original_handler)
            raise KeyboardInterrupt


class OperationTimer:
    """Track operation times for accurate ETA calculation using moving average."""

    def __init__(self, window_size=10):
        """
        Initialize timer with a sliding window for operation times.

        Args:
            window_size: Number of recent operations to track for averaging
        """
        self.times = []
        self.window_size = window_size

    def record(self):
        """Record timestamp of completed operation."""
        self.times.append(time.time())
        if len(self.times) > self.window_size:
            self.times.pop(0)

    def get_average_time_per_op(self):
        """
        Calculate average time per operation from recent history.

        Returns:
            Average seconds per operation, or None if insufficient data
        """
        if len(self.times) < 2:
            return None

        time_span = self.times[-1] - self.times[0]
        ops_completed = len(self.times) - 1
        return time_span / ops_completed if ops_completed > 0 else None

    def estimate_remaining(self, remaining_ops):
        """
        Estimate seconds remaining based on moving average.

        Args:
            remaining_ops: Number of operations left to complete

        Returns:
            Estimated seconds remaining, or None if insufficient data
        """
        avg_time = self.get_average_time_per_op()
        if avg_time is None:
            return None
        return remaining_ops * avg_time


# ============================================================================
# Validation Helper Functions
# ============================================================================

def validate_message_fields(header: Optional[str], body: Optional[str],
                            image_alt_text: Optional[str]) -> List[str]:
    """
    Validate message field lengths.

    Returns:
        List of error messages (empty if all valid)
    """
    errors = []

    if header and len(header) > 66:
        errors.append(f"Header text too long ({len(header)} chars). Maximum is 66 characters.")

    if body and len(body) > 144:
        errors.append(f"Body text too long ({len(body)} chars). Maximum is 144 characters.")

    if image_alt_text and len(image_alt_text) > 150:
        errors.append(f"Image alt text too long ({len(image_alt_text)} chars). Maximum is 150 characters.")

    return errors


def format_api_error(e: APIException) -> str:
    """Format an API exception into a readable error message."""
    error_msg = f"API Error {e.http_status_code}"
    if e.api_error:
        error_msg += f" ({e.api_error.name})"
    if e.error_message:
        error_msg += f": {e.error_message}"
    return error_msg


# ============================================================================
# CSV Parsing and Column Mapping Functions
# ============================================================================

def detect_column_mapping(csv_columns: List[str], args) -> Dict[str, str]:
    """
    Detect or create column mapping from CSV columns to API fields.

    Supports auto-detection with CLI overrides.

    Args:
        csv_columns: List of column names from CSV file
        args: CLI arguments with optional column overrides

    Returns:
        Dictionary mapping API field names to CSV column names
    """
    # Define common column name patterns (case-insensitive)
    patterns = {
        'message_id': ['message_id', 'message id', 'messageid', 'id'],
        'sandbox_message_id': ['sandbox message id', 'sandbox_message_id', 'sandbox messageid'],
        'header': ['header', 'title'],
        'body': ['body', 'message', 'text'],
        'locale': ['locale', 'locale shortcode', 'language', 'lang'],
        'image_id': ['image_id', 'image id', 'imageid', 'imageidentifier', 'image identifier'],
        'sandbox_image_id': ['sandbox image id', 'sandbox_image_id', 'sandbox imageid'],
        'image_alt_text': ['image_alt_text', 'alt text', 'alttext', 'alt_text', 'image alt'],
        'environment': ['environment', 'env'],
        'product_id': ['product_id', 'product id', 'productid', 'product']
    }

    # CLI overrides take precedence
    mapping = {}

    # Check for explicit CLI overrides
    if hasattr(args, 'col_message_id') and args.col_message_id:
        mapping['message_id'] = args.col_message_id
    if hasattr(args, 'col_header') and args.col_header:
        mapping['header'] = args.col_header
    if hasattr(args, 'col_body') and args.col_body:
        mapping['body'] = args.col_body
    if hasattr(args, 'col_locale') and args.col_locale:
        mapping['locale'] = args.col_locale
    if hasattr(args, 'col_image_id') and args.col_image_id:
        mapping['image_id'] = args.col_image_id
    if hasattr(args, 'col_alt_text') and args.col_alt_text:
        mapping['image_alt_text'] = args.col_alt_text
    if hasattr(args, 'col_product_id') and args.col_product_id:
        mapping['product_id'] = args.col_product_id

    # Auto-detect remaining columns
    csv_columns_lower = [col.lower() for col in csv_columns]

    for field, pattern_list in patterns.items():
        if field in mapping:
            continue  # Already mapped via CLI override

        for pattern in pattern_list:
            for i, col_lower in enumerate(csv_columns_lower):
                if pattern in col_lower:
                    mapping[field] = csv_columns[i]
                    break
            if field in mapping:
                break

    return mapping


def get_mapped_value(row: Dict[str, str], mapping: Dict[str, str],
                     field: str) -> Optional[str]:
    """
    Get a value from a CSV row using the column mapping.

    Args:
        row: CSV row as dictionary
        mapping: Column mapping dictionary
        field: API field name to retrieve

    Returns:
        Value from CSV or None if not found/empty
    """
    if field not in mapping:
        return None

    csv_column = mapping[field]
    value = row.get(csv_column, '').strip()

    return value if value else None


def get_environment_aware_value(row: Dict[str, str], mapping: Dict[str, str],
                                base_field: str, environment: str) -> Optional[str]:
    """
    Get a value from CSV row with environment-aware column selection.

    For SANDBOX environment: tries sandbox-specific column first, falls back to base column
    For PRODUCTION environment: uses base column only

    Args:
        row: CSV row as dictionary
        mapping: Column mapping dictionary
        base_field: Base field name (e.g., 'message_id', 'image_id')
        environment: Target environment ('SANDBOX' or 'PRODUCTION')

    Returns:
        Value from CSV or None if not found/empty
    """
    # For SANDBOX, try sandbox-specific column first
    if environment == 'SANDBOX':
        sandbox_field = f'sandbox_{base_field}'
        if sandbox_field in mapping:
            sandbox_value = get_mapped_value(row, mapping, sandbox_field)
            if sandbox_value:  # If sandbox column has a non-empty value, use it
                return sandbox_value

    # Fall back to base field (or use base field for PRODUCTION)
    return get_mapped_value(row, mapping, base_field)


def read_csv_file(csv_file_path: str) -> Tuple[List[str], List[Dict[str, str]]]:
    """
    Read a CSV file and return headers and rows.

    Args:
        csv_file_path: Path to CSV file

    Returns:
        Tuple of (column names, list of row dictionaries)
    """
    try:
        with open(csv_file_path, 'r', encoding='utf-8') as f:
            reader = csv.DictReader(f)
            columns = reader.fieldnames or []
            rows = list(reader)
            return columns, rows
    except FileNotFoundError:
        print(f"Error: CSV file not found: {csv_file_path}")
        sys.exit(1)
    except Exception as e:
        print(f"Error reading CSV file: {e}")
        sys.exit(1)


# ============================================================================
# Progress Reporting and Error Recovery
# ============================================================================

def print_progress(current: int, total: int, message: str = "Processing") -> None:
    """Print progress information (only in non-JSON mode)."""
    if total > 0:
        percentage = (current / total) * 100
        print(f"\r{message} row {current}/{total} ({percentage:.1f}%)...", end='', flush=True)


def parse_retry_after(exception: APIException) -> Optional[float]:
    """
    Parse Retry-After header from APIException.

    Args:
        exception: The APIException to parse

    Returns:
        Delay in seconds, or None if header not present
    """
    # Graceful fallback for missing response_headers attribute (not in upstream yet)
    if not hasattr(exception, 'response_headers') or not exception.response_headers:
        return None

    retry_after_value = exception.response_headers.get('retry-after') or exception.response_headers.get('Retry-After')
    if not retry_after_value:
        return None

    try:
        # Apple uses UNIX timestamp in milliseconds
        retry_after_ms = int(retry_after_value)
        current_time_ms = int(time.time() * 1000)

        # If value is large, it's likely a timestamp in milliseconds
        if retry_after_ms > current_time_ms:
            delay_ms = retry_after_ms - current_time_ms
            return max(0, delay_ms / 1000.0)
        else:
            # It's a delay in seconds
            return float(retry_after_ms)
    except (ValueError, TypeError):
        return None


def countdown_with_progress(seconds: float, attempt: int, max_retries: int) -> None:
    """
    Show countdown timer with progress bar and local clock time.

    Args:
        seconds: Number of seconds to count down
        attempt: Current attempt number (1-indexed)
        max_retries: Maximum number of retry attempts
    """
    end_time = time.time() + seconds
    target_clock = datetime.fromtimestamp(end_time)
    clock_str = target_clock.strftime("%I:%M:%S %p")

    while time.time() < end_time:
        remaining = int(end_time - time.time())
        if remaining < 0:
            break

        mins, secs = divmod(remaining, 60)

        # Progress bar
        bar_length = 30
        progress = 1 - (remaining / seconds) if seconds > 0 else 1
        filled = int(bar_length * progress)
        bar = '█' * filled + '░' * (bar_length - filled)

        print(f"\r  Retry {attempt}/{max_retries} at {clock_str} (in {mins:02d}:{secs:02d}) [{bar}]",
              end='', flush=True)
        time.sleep(0.5)

    print()  # New line after countdown


def format_time(seconds):
    """
    Format seconds into readable time string.

    Args:
        seconds: Number of seconds

    Returns:
        Formatted string like "45s", "7m 53s", or "2h 15m"
    """
    if seconds < 60:
        return f"{int(seconds)}s"
    elif seconds < 3600:
        mins = int(seconds / 60)
        secs = int(seconds % 60)
        return f"{mins}m {secs}s"
    else:
        hours = int(seconds / 3600)
        mins = int((seconds % 3600) / 60)
        return f"{hours}h {mins}m"


def print_operation_result(current: int, total: int, operation_name: str, status: str,
                           error_msg: str = None) -> None:
    """
    Print individual operation result (scrolls up with newline).

    Args:
        current: Current operation number
        total: Total operations
        operation_name: Operation description (e.g., "product_id / locale")
        status: Status symbol ('✓' success or '✗' failure)
        error_msg: Optional error message for failures
    """
    line = f"[{current}/{total}] {status} {operation_name}"
    if error_msg:
        line += f" - {error_msg}"
    print(line)


def print_progress_summary(current: int, total: int, stats: Dict[str, int], timer: OperationTimer) -> None:
    """
    Print/update summary line with progress bar and stats (stays at bottom, updates in place).

    Args:
        current: Current operation number
        total: Total operations
        stats: Stats dict with 'success', 'failure', 'rate_limited' counts
        timer: OperationTimer instance for ETA calculation
    """
    # Calculate actual progress percentage (current/total)
    percentage = (current / total) * 100

    # Build progress bar (20 characters)
    bar_length = 20
    filled = int(bar_length * (current / total))
    bar = '█' * filled + '░' * (bar_length - filled)

    # Calculate ETA from moving average
    remaining = total - current
    eta_seconds = timer.estimate_remaining(remaining)
    if eta_seconds:
        eta_str = format_time(eta_seconds)
    else:
        eta_str = "calculating..."

    # Build summary line with padding to clear previous content
    line = f"Progress: [{bar}] {percentage:5.1f}% | ✓{stats['success']} ✗{stats['failure']} ⏱{stats['rate_limited']} | ETA: {eta_str}"
    line = line.ljust(100)  # Pad to clear old content

    # Print with \r to overwrite
    print(f"\r{line}", end='', flush=True)


def generate_resume_command(args, remaining_product_ids: List[str], remaining_locales: List[str],
                            action_type: str) -> None:
    """
    Generate and print command to resume remaining operations.

    Args:
        args: Command-line arguments
        remaining_product_ids: List of product IDs that weren't attempted
        remaining_locales: List of locales that weren't attempted
        action_type: 'set-default' or 'delete-default'
    """
    print()
    print("=" * 70)
    print("TO RESUME REMAINING OPERATIONS, RUN:")
    print("=" * 70)
    print()

    print(f"python cli/retention_message.py \\")
    print(f"  --key-id \"{args.key_id}\" \\")
    print(f"  --issuer-id \"{args.issuer_id}\" \\")
    print(f"  --bundle-id \"{args.bundle_id}\" \\")
    print(f"  --p8-file \"{args.p8_file}\" \\")
    print(f"  --action {action_type} \\")

    # Add message-id for set-default
    if action_type == 'set-default' and hasattr(args, 'message_id'):
        print(f"  --message-id \"{args.message_id}\" \\")

    print(f"  --environment {args.environment} \\")

    # Add product IDs
    for product_id in remaining_product_ids:
        print(f"  --product-id \"{product_id}\" \\")

    # Add locales
    for i, locale in enumerate(remaining_locales):
        if i < len(remaining_locales) - 1:
            print(f"  --locale \"{locale}\" \\")
        else:
            print(f"  --locale \"{locale}\"")

    # Add note
    total_remaining = len(remaining_product_ids) * len(remaining_locales)
    print()
    print(f"Note: This will attempt {total_remaining} configuration(s) that were not completed.")


def estimate_completion_time(total_ops: int, completed_ops: int, rate_limit_delay: float) -> str:
    """
    Estimate time remaining for bulk operation.

    Args:
        total_ops: Total number of operations
        completed_ops: Number of completed operations
        rate_limit_delay: Delay per operation in seconds

    Returns:
        Formatted time string (e.g., "3h 12m" or "45s")
    """
    remaining_ops = total_ops - completed_ops
    estimated_seconds = remaining_ops * rate_limit_delay

    # Add 10% buffer for retries and overhead
    estimated_seconds *= 1.1

    mins, secs = divmod(int(estimated_seconds), 60)
    hours, mins = divmod(mins, 60)

    if hours > 0:
        return f"{hours}h {mins}m"
    elif mins > 0:
        return f"{mins}m {secs}s"
    else:
        return f"{secs}s"


def execute_with_countdown_retry(func, operation_name: str, max_retries: int = 5):
    """
    Execute a function with automatic retry and visual countdown on rate limit errors.

    Args:
        func: Function to execute (should be a lambda or callable)
        operation_name: Description of the operation for error messages
        max_retries: Maximum number of retry attempts

    Returns:
        Result of function execution

    Raises:
        APIException: If all retries are exhausted or non-retryable error occurs
    """
    for attempt in range(max_retries):
        try:
            return func()
        except APIException as e:
            # Only retry on rate limit errors
            if e.api_error == APIError.RATE_LIMIT_EXCEEDED:
                if attempt < max_retries - 1:
                    # Try to get Retry-After from headers
                    wait_time = parse_retry_after(e)

                    if wait_time is None:
                        # Fall back to exponential backoff: 2s, 4s, 8s, 16s, 32s
                        wait_time = 2 ** (attempt + 1)

                    # Cap at 60 seconds
                    wait_time = min(wait_time, 60)

                    # Show user-friendly message with target time
                    target_time = datetime.fromtimestamp(time.time() + wait_time)
                    clock_str = target_time.strftime("%I:%M:%S %p")
                    print(f"\n⚠ Rate limited! Retry after: {clock_str}")
                    countdown_with_progress(wait_time, attempt + 1, max_retries)
                    continue
            # Not a rate limit error or final attempt - re-raise
            raise

    # Should never reach here
    raise APIException(429, 4290000, "Rate limit exceeded after maximum retries")


def export_failed_rows(csv_file_path: str, failed_rows: List[Dict[str, Any]],
                       columns: List[str]) -> str:
    """
    Export failed rows to a new CSV file for retry.

    Args:
        csv_file_path: Original CSV file path
        failed_rows: List of failed row data (includes original row dict)
        columns: CSV column names

    Returns:
        Path to the failed rows CSV file
    """
    # Generate output filename
    base_path = Path(csv_file_path)
    output_path = base_path.parent / f"{base_path.stem}_failed{base_path.suffix}"

    try:
        with open(output_path, 'w', encoding='utf-8', newline='') as f:
            writer = csv.DictWriter(f, fieldnames=columns)
            writer.writeheader()

            for failed in failed_rows:
                if 'row_data' in failed:
                    writer.writerow(failed['row_data'])

        return str(output_path)
    except Exception as e:
        print(f"\nWarning: Failed to export error recovery CSV: {e}")
        return ""


def output_import_results(successes: List[Dict[str, Any]], failures: List[Dict[str, Any]],
                         skipped: List[Dict[str, Any]], action_name: str, args,
                         failed_csv_path: str = "") -> None:
    """
    Output results of CSV import operation.

    Args:
        successes: List of successful operations
        failures: List of failed operations
        skipped: List of skipped operations (already exist)
        action_name: Name of the action (e.g., "upload", "set-default")
        args: CLI arguments (contains json flag)
        failed_csv_path: Path to failed rows CSV (if created)
    """
    total = len(successes) + len(failures) + len(skipped)

    # Check if there are image-related errors
    image_errors = [f for f in failures if "image" in f.get("error", "").lower() and "404" in f.get("error", "")]
    has_image_errors = len(image_errors) > 0

    if args.json:
        result = {
            "status": "completed" if len(failures) == 0 else "partial",
            "action": action_name,
            "environment": args.environment,
            "total_rows": total,
            "successes": len(successes),
            "skipped": len(skipped),
            "failures": len(failures),
            "success_details": successes,
            "skipped_details": skipped,
            "failure_details": failures
        }
        if failed_csv_path:
            result["failed_rows_csv"] = failed_csv_path
        print(json.dumps(result, indent=2))
    else:
        print()  # New line after progress
        print(f"\n{'='*60}")
        print(f"CSV Import Results - {action_name}")
        print(f"{'='*60}")
        print(f"Total rows processed: {total}")
        print(f"Successful:          {len(successes)}")
        print(f"Skipped (exist):     {len(skipped)}")
        print(f"Failed:              {len(failures)}")

        if successes:
            print(f"\n✓ Successfully processed {len(successes)} row(s)")

        if skipped:
            print(f"ℹ Skipped {len(skipped)} existing message(s)")

        if failures:
            print(f"\n✗ Failed to process {len(failures)} row(s):")
            for failure in failures[:10]:  # Show first 10 failures
                row_num = failure.get('row', 'unknown')
                error = failure.get('error', 'unknown error')
                identifier = failure.get('message_id') or failure.get('product_id', '')
                if identifier:
                    print(f"  Row {row_num} ({identifier}): {error}")
                else:
                    print(f"  Row {row_num}: {error}")

            if len(failures) > 10:
                print(f"  ... and {len(failures) - 10} more errors")

            if failed_csv_path:
                print(f"\nFailed rows exported to: {failed_csv_path}")
                print("You can fix the issues and re-import this file.")

            # Show helpful suggestions for image errors
            if has_image_errors:
                print(f"\n💡 Image Error Solutions:")
                print(f"   {len(image_errors)} row(s) failed due to missing images.")
                print(f"   • Remove image_id and image_alt_text columns to upload without images")
                print(f"   • Upload images with those IDs first, then re-run message upload")
                print(f"   • Verify the correct image IDs for {args.environment} environment")
                if args.environment == "SANDBOX":
                    print(f"   • Check if 'Sandbox Image ID' column has correct values")

        print(f"{'='*60}\n")


def upload_message(args) -> None:
    """Upload a retention message."""
    client = create_api_client(args)

    # Generate message ID if not provided
    message_id = args.message_id if args.message_id else str(uuid.uuid4())

    # Validate message length constraints
    validation_errors = validate_message_fields(args.header, args.body, args.image_alt_text)
    if validation_errors:
        for error in validation_errors:
            print(f"Error: {error}")
        sys.exit(1)

    # Create image object if image parameters provided
    image = None
    if args.image_id or args.image_alt_text:
        image = UploadMessageImage(
            imageIdentifier=args.image_id,
            altText=args.image_alt_text
        )

    # Create request body
    request_body = UploadMessageRequestBody(
        header=args.header,
        body=args.body,
        image=image
    )

    try:
        client.upload_message(message_id, request_body)

        if args.json:
            print(json.dumps({
                "status": "success",
                "message_id": message_id,
                "header": args.header,
                "body": args.body,
                "environment": args.environment
            }))
        else:
            print(f"✓ Message uploaded successfully!")
            print(f"  Environment: {args.environment}")
            print(f"  Message ID: {message_id}")
            if args.header:
                print(f"  Header: {args.header}")
            if args.body:
                print(f"  Body: {args.body}")
            if image:
                print(f"  Image ID: {args.image_id}")
                print(f"  Alt Text: {args.image_alt_text}")

    except APIException as e:
        error_msg = f"API Error {e.http_status_code}"
        if e.api_error:
            error_msg += f" ({e.api_error.name})"
        if e.error_message:
            error_msg += f": {e.error_message}"

        if args.json:
            print(json.dumps({
                "status": "error",
                "error": error_msg,
                "http_status": e.http_status_code
            }))
        else:
            print(f"✗ {error_msg}")

        sys.exit(1)
    except Exception as e:
        if args.json:
            print(json.dumps({
                "status": "error",
                "error": str(e)
            }))
        else:
            print(f"✗ Unexpected error: {e}")
        sys.exit(1)


def list_messages(args) -> None:
    """List all retention messages."""
    client = create_api_client(args)

    try:
        response = client.get_message_list()

        if args.json:
            messages = []
            if response.messageIdentifiers:
                for msg in response.messageIdentifiers:
                    messages.append({
                        "message_id": msg.messageIdentifier,
                        "state": msg.messageState.value if msg.messageState else None
                    })
            print(json.dumps({
                "status": "success",
                "messages": messages,
                "total_count": len(messages),
                "environment": args.environment
            }))
        else:
            if not response.messageIdentifiers or len(response.messageIdentifiers) == 0:
                print(f"No retention messages found in {args.environment}.")
            else:
                print(f"Found {len(response.messageIdentifiers)} retention message(s) in {args.environment}:")
                print()
                for msg in response.messageIdentifiers:
                    state = msg.messageState.value if msg.messageState else "UNKNOWN"
                    print(f"  Message ID: {msg.messageIdentifier}")
                    print(f"  State:      {state}")
                    print()

    except APIException as e:
        error_msg = f"API Error {e.http_status_code}"
        if e.api_error:
            error_msg += f" ({e.api_error.name})"
        if e.error_message:
            error_msg += f": {e.error_message}"

        if args.json:
            print(json.dumps({
                "status": "error",
                "error": error_msg,
                "http_status": e.http_status_code
            }))
        else:
            print(f"✗ {error_msg}")

        sys.exit(1)
    except Exception as e:
        if args.json:
            print(json.dumps({
                "status": "error",
                "error": str(e)
            }))
        else:
            print(f"✗ Unexpected error: {e}")
        sys.exit(1)


def delete_message(args) -> None:
    """Delete a retention message."""
    if not args.message_id:
        print("Error: --message-id is required for delete action")
        sys.exit(1)

    client = create_api_client(args)

    try:
        client.delete_message(args.message_id)

        if args.json:
            print(json.dumps({
                "status": "success",
                "message_id": args.message_id,
                "action": "deleted",
                "environment": args.environment
            }))
        else:
            print(f"✓ Message deleted successfully!")
            print(f"  Environment: {args.environment}")
            print(f"  Message ID: {args.message_id}")

    except APIException as e:
        error_msg = f"API Error {e.http_status_code}"
        if e.api_error:
            error_msg += f" ({e.api_error.name})"
        if e.error_message:
            error_msg += f": {e.error_message}"

        if args.json:
            print(json.dumps({
                "status": "error",
                "error": error_msg,
                "http_status": e.http_status_code,
                "message_id": args.message_id
            }))
        else:
            print(f"✗ {error_msg}")

        sys.exit(1)
    except Exception as e:
        if args.json:
            print(json.dumps({
                "status": "error",
                "error": str(e),
                "message_id": args.message_id
            }))
        else:
            print(f"✗ Unexpected error: {e}")
        sys.exit(1)


def set_default_message(args) -> None:
    """Set a retention message as the default for one or more products and one or more locales."""
    if not args.message_id:
        print("Error: --message-id is required for set-default action")
        sys.exit(1)
    if not args.product_id:
        print("Error: --product-id is required for set-default action")
        sys.exit(1)

    client = create_api_client(args)
    # args.locale is a list due to action='append', default to ["en-US"] if not provided
    locales = args.locale if args.locale else ["en-US"]

    # Create request body
    request_body = DefaultConfigurationRequest(
        messageIdentifier=args.message_id
    )

    # args.product_id is a list due to action='append'
    product_ids = args.product_id
    successes = []
    failures = []

    # Calculate total operations for progress reporting
    total_operations = len(product_ids) * len(locales)
    current_operation = 0

    # Track statistics
    stats = {
        'success': 0,
        'failure': 0,
        'rate_limited': 0
    }

    # Determine rate limit delay for ETA estimation
    # SANDBOX: ~360 req/hour, PRODUCTION: ~3600 req/hour
    rate_limit_delay = 10.0 if args.environment == 'SANDBOX' else 1.0

    # Show initial estimate
    if not args.json and total_operations > 1:
        estimated_time = estimate_completion_time(total_operations, 0, rate_limit_delay)
        print(f"Starting bulk operation: {total_operations} configurations")
        print(f"Environment: {args.environment}")
        print(f"Estimated time (with rate limiting): ~{estimated_time}")
        print()

    # Track attempted operations for resume support
    attempted_operations = set()

    # Create timer for moving average ETA calculation
    timer = OperationTimer(window_size=10)

    # Iterate through all product × locale combinations with interrupt handling
    with InterruptHandler() as interrupt:
        for locale in locales:
            if interrupt.interrupted:
                break

            for product_id in product_ids:
                if interrupt.interrupted:
                    break

                # Mark this operation as attempted
                attempted_operations.add((product_id, locale))
                current_operation += 1
                operation_name = f"{product_id} / {locale}"

                try:
                    # Execute with automatic retry on rate limit
                    result = execute_with_countdown_retry(
                        lambda: client.configure_default_message(product_id, locale, request_body),
                        operation_name=operation_name,
                        max_retries=5
                    )
                    successes.append({"product_id": product_id, "locale": locale})
                    stats['success'] += 1
                    timer.record()  # Record completion time for ETA

                    # Show individual success result
                    if not args.json:
                        print_operation_result(current_operation, total_operations, operation_name, '✓')
                        # Update summary line
                        print_progress_summary(current_operation, total_operations, stats, timer)

                except APIException as e:
                    # Check if it's a rate limit error that exhausted retries
                    if e.api_error == APIError.RATE_LIMIT_EXCEEDED:
                        stats['rate_limited'] += 1

                    error_msg = f"API Error {e.http_status_code}"
                    if e.api_error:
                        error_msg += f" ({e.api_error.name})"
                    if e.error_message:
                        error_msg += f": {e.error_message}"
                    failures.append({"product_id": product_id, "locale": locale, "error": error_msg})
                    stats['failure'] += 1

                    # Show failure status
                    if not args.json:
                        eta = estimate_completion_time(total_operations, current_operation, rate_limit_delay)
                        print_operation_status(current_operation, total_operations, operation_name,
                                             '✗', stats, eta, error_msg=error_msg)

                except Exception as e:
                    failures.append({"product_id": product_id, "locale": locale, "error": str(e)})
                    stats['failure'] += 1

                    # Show failure status
                    if not args.json:
                        eta = estimate_completion_time(total_operations, current_operation, rate_limit_delay)
                        print_operation_status(current_operation, total_operations, operation_name,
                                             '✗', stats, eta, error_msg=str(e))

    # Calculate remaining (unattempted) operations
    all_operations = [(pid, loc) for pid in product_ids for loc in locales]
    remaining_operations = [(pid, loc) for (pid, loc) in all_operations
                           if (pid, loc) not in attempted_operations]
    skipped_count = len(remaining_operations)
    stats['skipped'] = skipped_count

    # Clear progress line
    if not args.json:
        print()
        print()

    # Output results
    if args.json:
        # Enhanced JSON output with skipped count
        print(json.dumps({
            "status": "completed" if len(failures) == 0 and skipped_count == 0 else "partial",
            "message_id": args.message_id,
            "locales": locales,
            "environment": args.environment,
            "total_products": len(product_ids),
            "total_locales": len(locales),
            "total_configurations": len(product_ids) * len(locales),
            "successes": successes,
            "failures": failures,
            "skipped": skipped_count
        }))
    else:
        # Enhanced summary output
        print("=" * 70)
        print("OPERATION SUMMARY")
        print("=" * 70)
        print(f"Total configurations: {total_operations}")
        print(f"✓ Succeeded:  {stats['success']}")
        print(f"✗ Failed:     {stats['failure']}")
        print(f"⊗ Skipped:    {skipped_count}")
        print(f"⏱ Rate limited: {stats['rate_limited']}")
        print()

        # Show success rate (of attempted)
        attempted_count = stats['success'] + stats['failure']
        if attempted_count > 0:
            success_rate = (stats['success'] / attempted_count) * 100
            print(f"Success rate: {success_rate:.1f}% (of attempted)")
            print()

        # Show detailed successes grouped by locale
        if successes:
            print("✓ Configured successfully:")
            from collections import defaultdict
            by_locale = defaultdict(list)
            for item in successes:
                by_locale[item['locale']].append(item['product_id'])

            for locale in sorted(by_locale.keys()):
                print(f"  {locale}: {len(by_locale[locale])} product(s)")

            print()

        # Show detailed failures
        if failures:
            print("✗ Failed configurations:")
            for failure in failures:
                print(f"  - {failure['product_id']} / {failure['locale']}: {failure['error']}")
            print()

        # Generate resume command for remaining operations
        if remaining_operations:
            # Extract unique product_ids and locales from remaining
            remaining_product_ids = sorted(set(pid for pid, loc in remaining_operations))
            remaining_locales = sorted(set(loc for pid, loc in remaining_operations))

            generate_resume_command(args, remaining_product_ids, remaining_locales, 'set-default')

    # Exit with error if any failures occurred or operations were skipped
    if failures or skipped_count > 0:
        sys.exit(1)


def delete_default_message(args) -> None:
    """Delete default message configuration for one or more products and one or more locales."""
    if not args.product_id:
        print("Error: --product-id is required for delete-default action")
        sys.exit(1)

    client = create_api_client(args)
    # args.locale is a list due to action='append', default to ["en-US"] if not provided
    locales = args.locale if args.locale else ["en-US"]

    # args.product_id is a list due to action='append'
    product_ids = args.product_id
    successes = []
    failures = []

    # Calculate total operations for progress reporting
    total_operations = len(product_ids) * len(locales)
    current_operation = 0

    # Track statistics
    stats = {
        'success': 0,
        'failure': 0,
        'rate_limited': 0
    }

    # Determine rate limit delay for ETA estimation
    # SANDBOX: ~360 req/hour, PRODUCTION: ~3600 req/hour
    rate_limit_delay = 10.0 if args.environment == 'SANDBOX' else 1.0

    # Show initial estimate
    if not args.json and total_operations > 1:
        estimated_time = estimate_completion_time(total_operations, 0, rate_limit_delay)
        print(f"Starting bulk operation: {total_operations} configurations")
        print(f"Environment: {args.environment}")
        print(f"Estimated time (with rate limiting): ~{estimated_time}")
        print()

    # Track attempted operations for resume support
    attempted_operations = set()

    # Create timer for moving average ETA calculation
    timer = OperationTimer(window_size=10)

    # Iterate through all product × locale combinations with interrupt handling
    with InterruptHandler() as interrupt:
        for locale in locales:
            if interrupt.interrupted:
                break

            for product_id in product_ids:
                if interrupt.interrupted:
                    break

                # Mark this operation as attempted
                attempted_operations.add((product_id, locale))
                current_operation += 1
                operation_name = f"{product_id} / {locale}"

                try:
                    # Execute with automatic retry on rate limit
                    result = execute_with_countdown_retry(
                        lambda: client.delete_default_message(product_id, locale),
                        operation_name=operation_name,
                        max_retries=5
                    )
                    successes.append({"product_id": product_id, "locale": locale})
                    stats['success'] += 1
                    timer.record()  # Record completion time for ETA

                    # Show individual success result
                    if not args.json:
                        print_operation_result(current_operation, total_operations, operation_name, '✓')
                        # Update summary line
                        print_progress_summary(current_operation, total_operations, stats, timer)

                except APIException as e:
                    # Check if it's a rate limit error that exhausted retries
                    if e.api_error == APIError.RATE_LIMIT_EXCEEDED:
                        stats['rate_limited'] += 1

                    error_msg = f"API Error {e.http_status_code}"
                    if e.api_error:
                        error_msg += f" ({e.api_error.name})"
                    if e.error_message:
                        error_msg += f": {e.error_message}"
                    failures.append({"product_id": product_id, "locale": locale, "error": error_msg})
                    stats['failure'] += 1

                    # Show individual failure result
                    if not args.json:
                        print_operation_result(current_operation, total_operations, operation_name,
                                             '✗', error_msg=error_msg)
                        # Update summary line
                        print_progress_summary(current_operation, total_operations, stats, timer)

                except Exception as e:
                    failures.append({"product_id": product_id, "locale": locale, "error": str(e)})
                    stats['failure'] += 1

                    # Show individual failure result
                    if not args.json:
                        print_operation_result(current_operation, total_operations, operation_name,
                                             '✗', error_msg=str(e))
                        # Update summary line
                        print_progress_summary(current_operation, total_operations, stats, timer)

    # Calculate remaining (unattempted) operations
    all_operations = [(pid, loc) for pid in product_ids for loc in locales]
    remaining_operations = [(pid, loc) for (pid, loc) in all_operations
                           if (pid, loc) not in attempted_operations]
    skipped_count = len(remaining_operations)
    stats['skipped'] = skipped_count

    # Clear progress line
    if not args.json:
        print()
        print()

    # Output results
    if args.json:
        # Enhanced JSON output with skipped count
        print(json.dumps({
            "status": "completed" if len(failures) == 0 and skipped_count == 0 else "partial",
            "locales": locales,
            "environment": args.environment,
            "action": "deleted_default",
            "total_products": len(product_ids),
            "total_locales": len(locales),
            "total_configurations": len(product_ids) * len(locales),
            "successes": successes,
            "failures": failures,
            "skipped": skipped_count
        }))
    else:
        # Enhanced summary output
        print("=" * 70)
        print("OPERATION SUMMARY")
        print("=" * 70)
        print(f"Total configurations: {total_operations}")
        print(f"✓ Succeeded:  {stats['success']}")
        print(f"✗ Failed:     {stats['failure']}")
        print(f"⊗ Skipped:    {skipped_count}")
        print(f"⏱ Rate limited: {stats['rate_limited']}")
        print()

        # Show success rate (of attempted)
        attempted_count = stats['success'] + stats['failure']
        if attempted_count > 0:
            success_rate = (stats['success'] / attempted_count) * 100
            print(f"Success rate: {success_rate:.1f}% (of attempted)")
            print()

        # Show detailed successes grouped by locale
        if successes:
            print("✓ Deleted successfully:")
            from collections import defaultdict
            by_locale = defaultdict(list)
            for item in successes:
                by_locale[item['locale']].append(item['product_id'])

            for locale in sorted(by_locale.keys()):
                print(f"  {locale}: {len(by_locale[locale])} product(s)")

            print()

        # Show detailed failures
        if failures:
            print("✗ Failed to delete:")
            for failure in failures:
                print(f"  - {failure['product_id']} / {failure['locale']}: {failure['error']}")
            print()

        # Generate resume command for remaining operations
        if remaining_operations:
            # Extract unique product_ids and locales from remaining
            remaining_product_ids = sorted(set(pid for pid, loc in remaining_operations))
            remaining_locales = sorted(set(loc for pid, loc in remaining_operations))

            generate_resume_command(args, remaining_product_ids, remaining_locales, 'delete-default')

    # Exit with error if any failures occurred or operations were skipped
    if failures or skipped_count > 0:
        sys.exit(1)


def import_csv_delete(args) -> None:
    """Bulk delete retention messages from a CSV file."""
    if not args.csv_file:
        print("Error: --csv-file is required for import-csv-delete action")
        sys.exit(1)

    # Read CSV file
    columns, rows = read_csv_file(args.csv_file)

    if not rows:
        print("Error: CSV file is empty")
        sys.exit(1)

    # Detect column mapping
    mapping = detect_column_mapping(columns, args)

    # Validate message_id column exists
    if 'message_id' not in mapping and 'sandbox_message_id' not in mapping:
        print("Error: Could not detect message_id column in CSV")
        print("\nAvailable columns:")
        for col in columns:
            print(f"  - {col}")
        print("\nUse --col-message-id='Column Name' to specify the message ID column.")
        sys.exit(1)

    # Extract message IDs from CSV
    message_ids_to_delete = []
    for idx, row in enumerate(rows, start=2):
        # Get message_id (prefer sandbox_message_id for SANDBOX environment)
        message_id = get_environment_aware_value(row, mapping, 'message_id', args.environment)
        if message_id:
            locale = get_mapped_value(row, mapping, 'locale') or 'unknown'
            message_ids_to_delete.append({
                'message_id': message_id,
                'locale': locale,
                'row': idx
            })

    if not message_ids_to_delete:
        print("Error: No message IDs found in CSV")
        sys.exit(1)

    # Create API client for pre-flight validation
    client = create_api_client(args)

    # Pre-flight: Fetch existing messages for validation
    if not args.json:
        print(f"Fetching existing messages from {args.environment}...")

    existing_message_ids = set()
    try:
        response = client.get_message_list()
        if response.messageIdentifiers:
            for msg in response.messageIdentifiers:
                existing_message_ids.add(msg.messageIdentifier)

        if not args.json:
            print(f"Found {len(existing_message_ids)} existing message(s)")
            print()
    except Exception as e:
        if not args.json:
            print(f"Warning: Could not fetch existing messages: {e}")
            print("Continuing without validation...\n")

    # Filter to only messages that actually exist
    messages_to_delete = []
    messages_not_found = []

    for item in message_ids_to_delete:
        if item['message_id'] in existing_message_ids:
            messages_to_delete.append(item)
        else:
            messages_not_found.append(item)

    # Show validation results
    if not args.json:
        print(f"Validation results:")
        print(f"  ✓ Found in API: {len(messages_to_delete)} messages (will delete)")
        print(f"  ⚠ Not found:    {len(messages_not_found)} messages (will skip)")
        print()

        if messages_not_found:
            print("Messages not found (already deleted or never existed):")
            for item in messages_not_found[:5]:  # Show first 5
                print(f"  - {item['message_id']} ({item['locale']})")
            if len(messages_not_found) > 5:
                print(f"  ... and {len(messages_not_found) - 5} more")
            print()

    # Check if anything to delete
    if len(messages_to_delete) == 0:
        if not args.json:
            print("No messages to delete (all messages in CSV already deleted or don't exist)")
        else:
            print(json.dumps({
                "status": "completed",
                "action": "import-csv-delete",
                "environment": args.environment,
                "total_messages": 0,
                "successes": [],
                "failures": [],
                "skipped": len(messages_not_found)
            }))
        return

    # Dry-run mode: just show what would be deleted
    if args.dry_run:
        if not args.json:
            print("=" * 70)
            print(f"IMPORT CSV DELETE - DRY RUN MODE")
            print("=" * 70)
            print(f"Messages to delete ({len(messages_to_delete)} total):")
            print()

            for i, item in enumerate(messages_to_delete, start=1):
                print(f"  [{i}] {item['message_id']} ({item['locale']})")

            print()
            print("=" * 70)
            print("This is a DRY RUN - no deletions will be performed.")
            print("Remove --dry-run to execute deletions.")
            print("=" * 70)
        else:
            print(json.dumps({
                "status": "dry_run",
                "action": "import-csv-delete",
                "environment": args.environment,
                "total_messages": len(messages_to_delete),
                "messages_found": [item['message_id'] for item in messages_to_delete],
                "messages_not_found": [item['message_id'] for item in messages_not_found],
                "skipped": len(messages_not_found)
            }))
        return

    # Actual deletion with progress tracking
    total_operations = len(messages_to_delete)
    current_operation = 0

    successes = []
    failures = []
    stats = {
        'success': 0,
        'failure': 0,
        'rate_limited': 0,
        'skipped': 0
    }

    # Show initial info
    if not args.json:
        print(f"Starting bulk delete: {total_operations} messages")
        print(f"Environment: {args.environment}")
        print()

    # Track attempted operations for resume support
    attempted_message_ids = set()

    # Create timer for ETA calculation
    timer = OperationTimer(window_size=10)

    # Iterate with interrupt handling
    with InterruptHandler() as interrupt:
        for item in messages_to_delete:
            if interrupt.interrupted:
                break

            message_id = item['message_id']
            locale = item['locale']
            row = item['row']

            # Mark as attempted
            attempted_message_ids.add(message_id)
            current_operation += 1

            try:
                # Execute with automatic retry on rate limit
                execute_with_countdown_retry(
                    lambda: client.delete_retention_message(message_id),
                    operation_name=f"{message_id} ({locale})",
                    max_retries=5
                )
                successes.append(message_id)
                stats['success'] += 1
                timer.record()

                # Show individual success result
                if not args.json:
                    print_operation_result(current_operation, total_operations,
                                         f"{message_id} ({locale})", '✓')
                    print_progress_summary(current_operation, total_operations, stats, timer)

            except APIException as e:
                if e.api_error == APIError.RATE_LIMIT_EXCEEDED:
                    stats['rate_limited'] += 1

                error_msg = f"API Error {e.http_status_code}"
                if e.api_error:
                    error_msg += f" ({e.api_error.name})"
                if e.error_message:
                    error_msg += f": {e.error_message}"
                failures.append({"message_id": message_id, "locale": locale, "row": row, "error": error_msg})
                stats['failure'] += 1

                if not args.json:
                    print_operation_result(current_operation, total_operations,
                                         f"{message_id} ({locale})", '✗', error_msg=error_msg)
                    print_progress_summary(current_operation, total_operations, stats, timer)

            except Exception as e:
                failures.append({"message_id": message_id, "locale": locale, "row": row, "error": str(e)})
                stats['failure'] += 1

                if not args.json:
                    print_operation_result(current_operation, total_operations,
                                         f"{message_id} ({locale})", '✗', error_msg=str(e))
                    print_progress_summary(current_operation, total_operations, stats, timer)

    # Calculate skipped operations
    # Skipped = messages we didn't attempt (interrupted) + messages not found in API
    skipped_from_interrupt = [item['message_id'] for item in messages_to_delete
                              if item['message_id'] not in attempted_message_ids]
    stats['skipped'] = len(skipped_from_interrupt) + len(messages_not_found)

    # Clear progress line
    if not args.json:
        print()
        print()

    # Output results
    if args.json:
        print(json.dumps({
            "status": "completed" if len(failures) == 0 and stats['skipped'] == 0 else "partial",
            "action": "import-csv-delete",
            "environment": args.environment,
            "total_messages": total_operations,
            "successes": successes,
            "failures": failures,
            "skipped": stats['skipped']
        }))
    else:
        print("=" * 70)
        print("OPERATION SUMMARY")
        print("=" * 70)
        print(f"Messages in CSV: {len(message_ids_to_delete)}")
        print(f"Found in API:    {total_operations}")
        print(f"Not found:       {len(messages_not_found)} (already deleted or never existed)")
        print()
        print(f"✓ Deleted:  {stats['success']}")
        print(f"✗ Failed:   {stats['failure']}")
        print(f"⊗ Skipped:  {len(skipped_from_interrupt)} (interrupted)")
        print(f"⏱ Rate limited: {stats['rate_limited']}")
        print()

        if stats['success'] > 0:
            attempted = stats['success'] + stats['failure']
            success_rate = (stats['success'] / attempted) * 100 if attempted > 0 else 0
            print(f"Success rate: {success_rate:.1f}% (of attempted)")
            print()

        if failures:
            print("✗ Failed deletions:")
            for failure in failures:
                print(f"  - {failure['message_id']} ({failure['locale']}): {failure['error']}")
            print()

        if messages_not_found and len(messages_not_found) <= 10:
            print("⚠ Messages not found (already deleted):")
            for item in messages_not_found:
                print(f"  - {item['message_id']} ({item['locale']})")
            print()

    # Exit with error if any failures or interrupted operations
    # (don't error on "not found" - those were already deleted)
    if failures or len(skipped_from_interrupt) > 0:
        sys.exit(1)


def import_csv(args) -> None:
    """Import and upload retention messages from a CSV file."""
    if not args.csv_file:
        print("Error: --csv-file is required for import-csv action")
        sys.exit(1)

    # Read CSV file
    columns, rows = read_csv_file(args.csv_file)

    if not rows:
        print("Error: CSV file is empty")
        sys.exit(1)

    # Detect column mapping
    mapping = detect_column_mapping(columns, args)

    # Display detected mapping in verbose mode
    if args.verbose and not args.json:
        env_label = f"for {args.environment} environment" if args.environment == 'SANDBOX' and 'sandbox_message_id' in mapping else ""
        print(f"Detected column mapping {env_label}:")
        for field, csv_col in mapping.items():
            # Show fallback info for sandbox fields
            if args.environment == 'SANDBOX' and field == 'message_id' and 'sandbox_message_id' in mapping:
                print(f"  {field:15} <- {mapping['sandbox_message_id']} (fallback: {csv_col})")
            elif args.environment == 'SANDBOX' and field == 'image_id' and 'sandbox_image_id' in mapping:
                print(f"  {field:15} <- {mapping['sandbox_image_id']} (fallback: {csv_col})")
            elif field not in ['sandbox_message_id', 'sandbox_image_id']:
                print(f"  {field:15} <- {csv_col}")
        print()

        print(f"Target environment: {args.environment}")
        if args.dry_run:
            print("Mode: DRY-RUN (no uploads will be performed)")
        print()

    # Validate required fields are mapped
    required_fields = ['message_id', 'header', 'body']
    # For sandbox, either message_id or sandbox_message_id is sufficient
    if args.environment == 'SANDBOX' and 'sandbox_message_id' in mapping:
        required_fields = [f for f in required_fields if f != 'message_id']
        required_fields.append('sandbox_message_id')

    missing_fields = [f for f in required_fields if f not in mapping]
    if 'sandbox_message_id' in missing_fields and 'message_id' in mapping:
        missing_fields.remove('sandbox_message_id')

    if missing_fields:
        print(f"Error: Could not detect required CSV columns: {', '.join(missing_fields)}")
        print("\nAvailable columns:")
        for col in columns:
            print(f"  - {col}")
        print("\nUse --col-<field> arguments to manually specify column names.")
        print("Example: --col-message-id='Message ID' --col-header='Header'")
        sys.exit(1)

    # Create API client
    client = create_api_client(args)

    # Pre-flight: Fetch existing messages for idempotent behavior
    if not args.json:
        print(f"Fetching existing messages from {args.environment}...")

    existing_message_ids = set()
    try:
        response = client.get_message_list()
        if response.messageIdentifiers:
            for msg in response.messageIdentifiers:
                existing_message_ids.add(msg.messageIdentifier)

        if not args.json and args.verbose:
            print(f"Found {len(existing_message_ids)} existing message(s)\n")
    except Exception as e:
        if not args.json:
            print(f"Warning: Could not fetch existing messages: {e}")
            print("Continuing without idempotent check...\n")

    # Pre-flight: Fetch existing images for validation
    if not args.json:
        print(f"Fetching existing images from {args.environment}...")

    existing_image_ids = set()
    try:
        image_response = client.get_image_list()
        if image_response.imageIdentifiers:
            for img in image_response.imageIdentifiers:
                # Only include APPROVED images (required for messages to display)
                if img.imageState and img.imageState.value == "APPROVED":
                    existing_image_ids.add(img.imageIdentifier)

        if not args.json and args.verbose:
            print(f"Found {len(existing_image_ids)} approved image(s)\n")
    except Exception as e:
        if not args.json:
            print(f"Warning: Could not fetch existing images: {e}")
            print("Continuing without image validation...\n")

    # Show sample/all rows (in both dry-run and normal mode)
    if not args.json:
        # Show all rows if verbose, otherwise just first 3
        rows_to_show = rows if args.verbose else rows[:3]
        row_label = "All rows to be processed:" if args.verbose else "Sample of first 3 rows to be processed:"

        print(row_label)
        for idx, row in enumerate(rows_to_show, start=2):
            message_id = get_environment_aware_value(row, mapping, 'message_id', args.environment)
            header = get_mapped_value(row, mapping, 'header')
            body = get_mapped_value(row, mapping, 'body')
            locale = get_mapped_value(row, mapping, 'locale')
            image_id = get_environment_aware_value(row, mapping, 'image_id', args.environment)
            image_alt_text = get_mapped_value(row, mapping, 'image_alt_text')

            status = "SKIP (already exists)" if message_id and message_id in existing_message_ids else "UPLOAD (new)"

            print(f"  Row {idx}:")
            print(f"    message_id: {message_id}")
            if header:
                print(f"    header: \"{header}\"")
            if body:
                print(f"    body: \"{body}\"")
            if locale:
                print(f"    locale: {locale}")
            if image_id:
                # Check if image exists and show warning if not
                image_warning = ""
                if image_id not in existing_image_ids:
                    image_warning = " ⚠ (not found)"
                print(f"    image_id: {image_id}{image_warning}")
            if image_alt_text:
                print(f"    image_alt_text: \"{image_alt_text}\"")
            print(f"    → {status}")
            print()

        if not args.verbose and len(rows) > 3:
            print(f"  ... (showing 3 of {len(rows)} rows, use --verbose to see all)\n")

    # Calculate pre-upload summary (always show, not just in dry-run)
    if not args.json:
        will_skip_count = 0
        rows_with_invalid_images = 0

        for row in rows:
            message_id = get_environment_aware_value(row, mapping, 'message_id', args.environment)
            if message_id and message_id in existing_message_ids:
                will_skip_count += 1

            # Check if row has an image that doesn't exist
            image_id = get_environment_aware_value(row, mapping, 'image_id', args.environment)
            if image_id and image_id not in existing_image_ids:
                rows_with_invalid_images += 1

        will_upload_count = len(rows) - will_skip_count

        print("Pre-upload Summary:")
        print(f"  Total rows: {len(rows)}")
        print(f"  Will skip (already exist): {will_skip_count}")
        print(f"  Will attempt upload: {will_upload_count}")
        if rows_with_invalid_images > 0:
            print(f"  ⚠ Rows with missing images: {rows_with_invalid_images} (uploads will likely fail)")
        print()

    # Process rows
    successes = []
    failures = []
    skipped = []
    total_rows = len(rows)

    for idx, row in enumerate(rows, start=2):  # Start at 2 (header is row 1)
        # Show progress (only in non-JSON mode)
        if not args.json:
            print_progress(idx - 1, total_rows, "Processing")

        try:
            # Extract fields from CSV (use environment-aware values for message_id and image_id)
            message_id = get_environment_aware_value(row, mapping, 'message_id', args.environment)
            header = get_mapped_value(row, mapping, 'header')
            body = get_mapped_value(row, mapping, 'body')
            image_id = get_environment_aware_value(row, mapping, 'image_id', args.environment)
            image_alt_text = get_mapped_value(row, mapping, 'image_alt_text')

            # Skip rows with missing required fields
            if not message_id:
                failures.append({
                    "row": idx,
                    "error": "Missing message_id",
                    "row_data": row
                })
                continue

            # Skip if message already exists (idempotent behavior)
            if message_id in existing_message_ids:
                skipped.append({
                    "row": idx,
                    "message_id": message_id,
                    "reason": "already exists"
                })
                continue

            # Validate field lengths
            validation_errors = validate_message_fields(header, body, image_alt_text)
            if validation_errors:
                failures.append({
                    "row": idx,
                    "message_id": message_id,
                    "error": "; ".join(validation_errors),
                    "row_data": row
                })
                continue

            # Skip dry-run API call
            if args.dry_run:
                successes.append({
                    "row": idx,
                    "message_id": message_id,
                    "action": "dry-run"
                })
                continue

            # Create image object if image parameters provided
            image = None
            if image_id or image_alt_text:
                image = UploadMessageImage(
                    imageIdentifier=image_id,
                    altText=image_alt_text
                )

            # Create request body
            request_body = UploadMessageRequestBody(
                header=header,
                body=body,
                image=image
            )

            # Upload message
            client.upload_message(message_id, request_body)
            successes.append({
                "row": idx,
                "message_id": message_id,
                "header": header[:30] + "..." if header and len(header) > 30 else header
            })

        except APIException as e:
            # Handle "already exists" error specially (shouldn't happen with pre-flight check, but just in case)
            if e.http_status_code == 409 or (e.api_error and '4090001' in str(e.api_error)):
                skipped.append({
                    "row": idx,
                    "message_id": message_id if 'message_id' in locals() else None,
                    "reason": "already exists (API confirmed)"
                })
            else:
                error_msg = format_api_error(e)
                # Add helpful context for image errors
                if e.http_status_code == 404 and "image" in error_msg.lower():
                    image_id_used = get_environment_aware_value(row, mapping, 'image_id', args.environment)
                    error_msg += f" (image_id: {image_id_used})"

                failures.append({
                    "row": idx,
                    "message_id": message_id if 'message_id' in locals() else None,
                    "error": error_msg,
                    "row_data": row
                })
        except Exception as e:
            failures.append({
                "row": idx,
                "error": str(e),
                "row_data": row
            })

    # Export failed rows if any
    failed_csv_path = ""
    if failures and not args.dry_run:
        failed_csv_path = export_failed_rows(args.csv_file, failures, columns)

    # Output results
    action_name = "import-csv (dry-run)" if args.dry_run else "import-csv"
    output_import_results(successes, failures, skipped, action_name, args, failed_csv_path)

    # Exit with error if any failures occurred
    if failures:
        sys.exit(1)


def import_csv_defaults(args) -> None:
    """Import and configure default messages from a CSV file."""
    if not args.csv_file:
        print("Error: --csv-file is required for import-csv-defaults action")
        sys.exit(1)

    # Read CSV file
    columns, rows = read_csv_file(args.csv_file)

    if not rows:
        print("Error: CSV file is empty")
        sys.exit(1)

    # Detect column mapping
    mapping = detect_column_mapping(columns, args)

    # Display detected mapping in verbose mode
    if args.verbose and not args.json:
        env_label = f"for {args.environment} environment" if args.environment == 'SANDBOX' and 'sandbox_message_id' in mapping else ""
        print(f"Detected column mapping {env_label}:")
        for field, csv_col in mapping.items():
            # Show fallback info for sandbox fields
            if args.environment == 'SANDBOX' and field == 'message_id' and 'sandbox_message_id' in mapping:
                print(f"  {field:15} <- {mapping['sandbox_message_id']} (fallback: {csv_col})")
            elif field not in ['sandbox_message_id', 'sandbox_image_id']:
                print(f"  {field:15} <- {csv_col}")
        print()

        print(f"Target environment: {args.environment}")
        if args.dry_run:
            print("Mode: DRY-RUN (no API calls will be made)")
        print()

    # Validate required fields are mapped
    required_fields = ['message_id', 'locale']
    missing_fields = [f for f in required_fields if f not in mapping]
    if missing_fields:
        print(f"Error: Could not detect required CSV columns: {', '.join(missing_fields)}")
        print("\nAvailable columns:")
        for col in columns:
            print(f"  - {col}")
        print("\nUse --col-<field> arguments to manually specify column names.")
        print("Example: --col-message-id='Message ID' --col-locale='Locale shortcode'")
        sys.exit(1)

    # Check for product_id - either from CLI or CSV
    has_product_id_column = 'product_id' in mapping
    has_product_id_cli = args.product_id is not None and len(args.product_id) > 0

    if not has_product_id_column and not has_product_id_cli:
        print("Error: Product ID must be specified either via --product-id flag or as a CSV column")
        sys.exit(1)

    # Create API client
    client = create_api_client(args)

    # Process rows
    successes = []
    failures = []
    skipped = []
    total_rows = len(rows)

    for idx, row in enumerate(rows, start=2):  # Start at 2 (header is row 1)
        # Show progress (only in non-JSON mode)
        if not args.json:
            print_progress(idx - 1, total_rows, "Processing")

        try:
            # Extract fields from CSV (use environment-aware value for message_id)
            message_id = get_environment_aware_value(row, mapping, 'message_id', args.environment)
            locale = get_mapped_value(row, mapping, 'locale')

            # Determine product IDs - CLI takes precedence over CSV
            if has_product_id_cli:
                product_ids = args.product_id
            else:
                csv_product_id = get_mapped_value(row, mapping, 'product_id')
                if not csv_product_id:
                    failures.append({
                        "row": idx,
                        "error": "Missing product_id",
                        "row_data": row
                    })
                    continue
                product_ids = [csv_product_id]

            # Skip rows with missing required fields
            if not message_id:
                failures.append({
                    "row": idx,
                    "error": "Missing message_id",
                    "row_data": row
                })
                continue

            if not locale:
                failures.append({
                    "row": idx,
                    "message_id": message_id,
                    "error": "Missing locale",
                    "row_data": row
                })
                continue

            # Skip dry-run API call
            if args.dry_run:
                successes.append({
                    "row": idx,
                    "message_id": message_id,
                    "locale": locale,
                    "product_ids": product_ids,
                    "action": "dry-run"
                })
                continue

            # Create request body
            request_body = DefaultConfigurationRequest(
                messageIdentifier=message_id
            )

            # Configure default for each product ID
            row_successes = []
            row_failures = []
            for product_id in product_ids:
                try:
                    client.configure_default_retention_message(product_id, locale, request_body)
                    row_successes.append(product_id)
                except APIException as e:
                    row_failures.append({
                        "product_id": product_id,
                        "error": format_api_error(e)
                    })
                except Exception as e:
                    row_failures.append({
                        "product_id": product_id,
                        "error": str(e)
                    })

            # Record results for this row
            if row_successes:
                successes.append({
                    "row": idx,
                    "message_id": message_id,
                    "locale": locale,
                    "product_ids": row_successes
                })

            if row_failures:
                for failure in row_failures:
                    failures.append({
                        "row": idx,
                        "message_id": message_id,
                        "locale": locale,
                        "product_id": failure["product_id"],
                        "error": failure["error"],
                        "row_data": row
                    })

        except Exception as e:
            failures.append({
                "row": idx,
                "error": str(e),
                "row_data": row
            })

    # Export failed rows if any
    failed_csv_path = ""
    if failures and not args.dry_run:
        failed_csv_path = export_failed_rows(args.csv_file, failures, columns)

    # Output results
    action_name = "import-csv-defaults (dry-run)" if args.dry_run else "import-csv-defaults"
    output_import_results(successes, failures, skipped, action_name, args, failed_csv_path)

    # Exit with error if any failures occurred
    if failures:
        sys.exit(1)


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="Manage App Store retention messages",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Upload a message with auto-generated ID
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --header "Welcome back!" --body "New features await"

  # Upload with specific message ID and image
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --message-id my-msg-001 --header "Sale!" \\
           --body "50%% off premium features" --image-id banner-001 \\
           --image-alt-text "Sale banner"

  # List all messages
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --action list

  # Delete a message
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --action delete --message-id my-msg-001

  # Set a message as default for a single product and locale
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --action set-default --message-id my-msg-001 \\
           --product-id com.example.premium --locale en-US

  # Set a message as default for multiple products
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --action set-default --message-id my-msg-001 \\
           --product-id com.example.premium --product-id com.example.basic \\
           --locale en-US

  # Delete default message configuration for multiple products
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --action delete-default \\
           --product-id com.example.premium --product-id com.example.basic \\
           --locale en-US

  # Production environment
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --environment PRODUCTION --action list

  # Import messages from CSV (auto-detect columns)
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --action import-csv --csv-file messages.csv

  # Import messages with dry-run to validate
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --action import-csv --csv-file messages.csv --dry-run

  # Import messages with custom column mapping
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --action import-csv --csv-file messages.csv \\
           --col-message-id="Message ID" --col-header="Header (Max 66 characters)"

  # Configure default messages from CSV with CLI product ID
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --action import-csv-defaults --csv-file messages.csv \\
           --product-id com.example.premium

  # Configure default messages from CSV using product_id column
  %(prog)s --key-id KEY123 --issuer-id ISS456 --bundle-id com.example.app \\
           --p8-file key.p8 --action import-csv-defaults --csv-file messages.csv

Error Codes:
  4000164 - Invalid locale
  4000023 - Invalid product ID
  4010001 - Header text too long (max 66 characters)
  4010002 - Body text too long (max 144 characters)
  4010003 - Alt text too long (max 150 characters)
  4010004 - Maximum number of messages reached
  4030017 - Message not approved
  4030018 - Image not approved
  4040001 - Message not found
  4090001 - Message with this ID already exists
        """
    )

    # Required arguments for all actions
    required_group = parser.add_argument_group('required arguments')
    required_group.add_argument(
        '--key-id',
        required=True,
        help='Private key ID from App Store Connect (e.g., "ABCDEFGHIJ")'
    )
    required_group.add_argument(
        '--issuer-id',
        required=True,
        help='Issuer ID from App Store Connect'
    )
    required_group.add_argument(
        '--bundle-id',
        required=True,
        help='App bundle identifier (e.g., "com.example.myapp")'
    )
    required_group.add_argument(
        '--p8-file',
        required=True,
        help='Path to .p8 private key file'
    )

    # Action selection
    parser.add_argument(
        '--action',
        choices=['upload', 'list', 'delete', 'set-default', 'delete-default', 'import-csv', 'import-csv-defaults', 'import-csv-delete'],
        default='upload',
        help='Action to perform (default: upload)'
    )

    # Message content arguments (for upload)
    content_group = parser.add_argument_group('message content (upload only)')
    content_group.add_argument(
        '--message-id',
        help='Unique message identifier (UUID format). Auto-generated if not provided for upload.'
    )
    content_group.add_argument(
        '--header',
        help='Header text (max 66 characters)'
    )
    content_group.add_argument(
        '--body',
        help='Body text (max 144 characters)'
    )
    content_group.add_argument(
        '--image-id',
        help='Image identifier for optional image'
    )
    content_group.add_argument(
        '--image-alt-text',
        help='Alternative text for image (max 150 characters)'
    )

    # Default message configuration arguments
    default_group = parser.add_argument_group('default message configuration (set-default and delete-default)')
    default_group.add_argument(
        '--product-id',
        action='append',
        help='Product identifier (e.g., subscription product ID). Can be specified multiple times for bulk operations.'
    )
    default_group.add_argument(
        '--locale',
        action='append',
        help='Locale code (e.g., "en-US", "fr-FR"). Can be specified multiple times for bulk operations. Default: en-US if not specified'
    )

    # CSV import arguments
    csv_group = parser.add_argument_group('CSV import (import-csv and import-csv-defaults)')
    csv_group.add_argument(
        '--csv-file',
        help='Path to CSV file for bulk import operations'
    )
    csv_group.add_argument(
        '--dry-run',
        action='store_true',
        help='Validate CSV and show what would be processed without making actual API calls'
    )
    csv_group.add_argument(
        '--col-message-id',
        help='CSV column name for message_id (auto-detected if not specified)'
    )
    csv_group.add_argument(
        '--col-header',
        help='CSV column name for header text (auto-detected if not specified)'
    )
    csv_group.add_argument(
        '--col-body',
        help='CSV column name for body text (auto-detected if not specified)'
    )
    csv_group.add_argument(
        '--col-locale',
        help='CSV column name for locale (auto-detected if not specified)'
    )
    csv_group.add_argument(
        '--col-image-id',
        help='CSV column name for image_id (auto-detected if not specified)'
    )
    csv_group.add_argument(
        '--col-alt-text',
        help='CSV column name for image alt text (auto-detected if not specified)'
    )
    csv_group.add_argument(
        '--col-product-id',
        help='CSV column name for product_id (auto-detected if not specified)'
    )

    # Global options
    parser.add_argument(
        '--environment',
        choices=['SANDBOX', 'PRODUCTION'],
        default='SANDBOX',
        help='App Store environment (default: SANDBOX)'
    )
    parser.add_argument(
        '--json',
        action='store_true',
        help='Output results in JSON format'
    )
    parser.add_argument(
        '--verbose',
        action='store_true',
        help='Enable verbose output'
    )

    args = parser.parse_args()

    # Validate arguments based on action
    if args.action == 'delete' and not args.message_id:
        parser.error("--message-id is required for delete action")
    if args.action == 'set-default':
        if not args.message_id:
            parser.error("--message-id is required for set-default action")
        if not args.product_id:
            parser.error("--product-id is required for set-default action")
    if args.action == 'delete-default' and not args.product_id:
        parser.error("--product-id is required for delete-default action")
    if args.action in ['import-csv', 'import-csv-defaults']:
        if not args.csv_file:
            parser.error(f"--csv-file is required for {args.action} action")
        if not os.path.isfile(args.csv_file):
            parser.error(f"CSV file not found: {args.csv_file}")

    # Validate file exists
    if not os.path.isfile(args.p8_file):
        print(f"Error: Private key file not found: {args.p8_file}")
        sys.exit(1)

    # Execute the appropriate action
    if args.action == 'upload':
        upload_message(args)
    elif args.action == 'list':
        list_messages(args)
    elif args.action == 'delete':
        delete_message(args)
    elif args.action == 'set-default':
        set_default_message(args)
    elif args.action == 'delete-default':
        delete_default_message(args)
    elif args.action == 'import-csv':
        import_csv(args)
    elif args.action == 'import-csv-defaults':
        import_csv_defaults(args)
    elif args.action == 'import-csv-delete':
        import_csv_delete(args)


if __name__ == '__main__':
    main()