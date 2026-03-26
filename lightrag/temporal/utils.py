"""
Temporal utilities for timezone handling and date validation.

This module provides comprehensive timezone-aware date handling and validation
for temporal RAG operations.

Phase 2 Fixes:
- Issue #4: Missing Timezone Handling
- Issue #5: No Date Validation
"""

import os
from datetime import datetime, timezone
from typing import Optional, Tuple
from zoneinfo import ZoneInfo

from lightrag.utils import logger


class TemporalUtils:
    """Timezone-aware temporal utilities."""

    # Default timezone from environment or UTC
    DEFAULT_TIMEZONE = os.getenv("LIGHTRAG_TIMEZONE", "UTC")

    # Supported date formats
    DATE_FORMATS = [
        "%Y-%m-%dT%H:%M:%S%z",  # ISO 8601 with timezone: 2024-01-01T12:00:00+00:00
        "%Y-%m-%dT%H:%M:%SZ",  # ISO 8601 UTC: 2024-01-01T12:00:00Z
        "%Y-%m-%dT%H:%M:%S",  # ISO 8601 no timezone: 2024-01-01T12:00:00
        "%Y-%m-%d %H:%M:%S",  # Standard datetime: 2024-01-01 12:00:00
        "%Y-%m-%d",  # Date only: 2024-01-01
    ]

    @staticmethod
    def parse_date_with_timezone(
        date_str: str, default_tz: Optional[str] = None
    ) -> datetime:
        """
        Parse date string with timezone awareness.

        Args:
            date_str: Date string in various formats
            default_tz: Default timezone if not specified in string (defaults to LIGHTRAG_TIMEZONE)

        Returns:
            Timezone-aware datetime object

        Raises:
            ValueError: If date format is invalid

        Examples:
            >>> TemporalUtils.parse_date_with_timezone("2024-01-01T12:00:00+00:00")
            datetime.datetime(2024, 1, 1, 12, 0, tzinfo=datetime.timezone.utc)

            >>> TemporalUtils.parse_date_with_timezone("2024-01-01")
            datetime.datetime(2024, 1, 1, 0, 0, tzinfo=datetime.timezone.utc)
        """
        if not date_str or date_str.lower() == "unknown":
            raise ValueError("Date string is empty or 'unknown'")

        # Try each format
        for fmt in TemporalUtils.DATE_FORMATS:
            try:
                dt = datetime.strptime(date_str.strip(), fmt)

                # If no timezone info, apply default
                if dt.tzinfo is None:
                    tz_name = default_tz or TemporalUtils.DEFAULT_TIMEZONE
                    try:
                        tz = ZoneInfo(tz_name)
                    except Exception:
                        logger.warning(f"Invalid timezone '{tz_name}', using UTC")
                        tz = timezone.utc
                    dt = dt.replace(tzinfo=tz)

                return dt

            except ValueError:
                continue

        raise ValueError(
            f"Invalid date format: '{date_str}'. "
            f"Supported formats: {', '.join(TemporalUtils.DATE_FORMATS)}"
        )

    @staticmethod
    def normalize_to_utc(dt: datetime) -> datetime:
        """
        Normalize datetime to UTC for consistent comparisons.

        Args:
            dt: Datetime object (timezone-aware or naive)

        Returns:
            UTC datetime

        Examples:
            >>> dt = datetime(2024, 1, 1, 12, 0, tzinfo=ZoneInfo("America/New_York"))
            >>> TemporalUtils.normalize_to_utc(dt)
            datetime.datetime(2024, 1, 1, 17, 0, tzinfo=datetime.timezone.utc)
        """
        if dt.tzinfo is None:
            # Assume UTC for naive datetimes
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)

    @staticmethod
    def format_date_iso(dt: datetime) -> str:
        """
        Format datetime as ISO 8601 string with timezone.

        Args:
            dt: Datetime object

        Returns:
            ISO 8601 formatted string

        Examples:
            >>> dt = datetime(2024, 1, 1, 12, 0, tzinfo=timezone.utc)
            >>> TemporalUtils.format_date_iso(dt)
            '2024-01-01T12:00:00+00:00'
        """
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.isoformat()

    @staticmethod
    def compare_dates(date1: str, date2: str) -> int:
        """
        Compare two date strings.

        Args:
            date1: First date string
            date2: Second date string

        Returns:
            -1 if date1 < date2, 0 if equal, 1 if date1 > date2

        Raises:
            ValueError: If either date is invalid
        """
        dt1 = TemporalUtils.normalize_to_utc(
            TemporalUtils.parse_date_with_timezone(date1)
        )
        dt2 = TemporalUtils.normalize_to_utc(
            TemporalUtils.parse_date_with_timezone(date2)
        )

        if dt1 < dt2:
            return -1
        elif dt1 > dt2:
            return 1
        else:
            return 0


class DateValidator:
    """Comprehensive date validation with semantic checks."""

    # Validation bounds
    MIN_YEAR = 1900
    MAX_YEAR = 2100

    @staticmethod
    def validate_date_string(date_str: str) -> Tuple[bool, Optional[str]]:
        """
        Validate date string comprehensively.

        Args:
            date_str: Date string to validate

        Returns:
            Tuple of (is_valid, error_message)
            - is_valid: True if valid, False otherwise
            - error_message: None if valid, error description if invalid

        Examples:
            >>> DateValidator.validate_date_string("2024-02-29")
            (True, None)

            >>> DateValidator.validate_date_string("2023-02-29")
            (False, "2023 is not a leap year")

            >>> DateValidator.validate_date_string("2024-13-01")
            (False, "Invalid date format: ...")
        """
        # Allow "unknown" as valid placeholder
        if not date_str or date_str.lower() == "unknown":
            return True, None

        try:
            # Parse date
            dt = TemporalUtils.parse_date_with_timezone(date_str)

            # Year bounds check
            if dt.year < DateValidator.MIN_YEAR:
                return (
                    False,
                    f"Year {dt.year} too far in past (min: {DateValidator.MIN_YEAR})",
                )
            if dt.year > DateValidator.MAX_YEAR:
                return (
                    False,
                    f"Year {dt.year} too far in future (max: {DateValidator.MAX_YEAR})",
                )

            # Leap year check for February 29
            if dt.month == 2 and dt.day == 29:
                if not DateValidator.is_leap_year(dt.year):
                    return False, f"{dt.year} is not a leap year"

            # Future date warning (not error)
            now = datetime.now(timezone.utc)
            if dt > now:
                logger.warning(f"Date {date_str} is in the future")

            return True, None

        except ValueError as e:
            return False, str(e)

    @staticmethod
    def is_leap_year(year: int) -> bool:
        """
        Check if year is a leap year.

        Args:
            year: Year to check

        Returns:
            True if leap year, False otherwise

        Examples:
            >>> DateValidator.is_leap_year(2024)
            True
            >>> DateValidator.is_leap_year(2023)
            False
            >>> DateValidator.is_leap_year(2000)
            True
            >>> DateValidator.is_leap_year(1900)
            False
        """
        return (year % 4 == 0 and year % 100 != 0) or (year % 400 == 0)

    @staticmethod
    def validate_date_range(
        start_date: str, end_date: str
    ) -> Tuple[bool, Optional[str]]:
        """
        Validate that start_date <= end_date.

        Args:
            start_date: Start date string
            end_date: End date string

        Returns:
            Tuple of (is_valid, error_message)

        Examples:
            >>> DateValidator.validate_date_range("2024-01-01", "2024-12-31")
            (True, None)

            >>> DateValidator.validate_date_range("2024-12-31", "2024-01-01")
            (False, "Start date must be before or equal to end date")
        """
        # Validate individual dates first
        valid_start, error_start = DateValidator.validate_date_string(start_date)
        if not valid_start:
            return False, f"Invalid start date: {error_start}"

        valid_end, error_end = DateValidator.validate_date_string(end_date)
        if not valid_end:
            return False, f"Invalid end date: {error_end}"

        # Compare dates
        try:
            if TemporalUtils.compare_dates(start_date, end_date) > 0:
                return False, "Start date must be before or equal to end date"
            return True, None
        except ValueError as e:
            return False, str(e)


def validate_and_parse_date(date_str: str, field_name: str = "date") -> datetime:
    """
    Convenience function to validate and parse date in one step.

    Args:
        date_str: Date string to validate and parse
        field_name: Name of field for error messages

    Returns:
        Parsed datetime object

    Raises:
        ValueError: If date is invalid

    Examples:
        >>> dt = validate_and_parse_date("2024-01-01", "effective_date")
        >>> dt.year
        2024
    """
    is_valid, error = DateValidator.validate_date_string(date_str)
    if not is_valid:
        raise ValueError(f"Invalid {field_name}: {error}")

    return TemporalUtils.parse_date_with_timezone(date_str)


#
