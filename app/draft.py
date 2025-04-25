import unittest
from .calendar_api import get_calendar_service

class MyTestCase(unittest.TestCase):
    def test_something(self):
        service = get_calendar_service()
        print(service)
        self.assertEqual(True, True)  # add assertion here


if __name__ == '__main__':
    unittest.main()


