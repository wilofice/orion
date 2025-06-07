#!/usr/bin/env python3
"""Quick test script to verify UserPreferences validation works."""
import sys
sys.path.append('/Users/genereux/PycharmProjects/orion')

from datetime import timedelta
from app.models import UserPreferences

print("Testing UserPreferences with minimal data...")
try:
    # Test with just user_id (should work with defaults)
    prefs1 = UserPreferences(user_id="test_user")
    print("✓ Created with just user_id")
    print(f"  - timezone: {prefs1.time_zone}")
    print(f"  - working_hours count: {len(prefs1.working_hours)}")
    print(f"  - preferred_break_duration: {prefs1.preferred_break_duration}")
    print(f"  - work_block_max_duration: {prefs1.work_block_max_duration}")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\nTesting UserPreferences with empty values...")
try:
    # Test with empty values that should trigger defaults
    prefs2 = UserPreferences(
        user_id="test_user",
        time_zone="",
        working_hours={}
    )
    print("✓ Created with empty time_zone and working_hours")
    print(f"  - timezone: {prefs2.time_zone}")
    print(f"  - working_hours count: {len(prefs2.working_hours)}")
except Exception as e:
    print(f"✗ Failed: {e}")

print("\nTesting UserPreferences with zero duration (should fail)...")
try:
    prefs3 = UserPreferences(
        user_id="test_user",
        preferred_break_duration=timedelta(0)
    )
    print("✗ Unexpected success - should have failed validation")
except ValueError as e:
    print(f"✓ Correctly rejected zero duration: {e}")

print("\nAll tests completed!")