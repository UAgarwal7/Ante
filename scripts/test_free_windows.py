"""Interval arithmetic for study-block scheduling.

These exist because the whole point of computing slots in code rather than in
the model is that the arithmetic is checkable. Pure functions only -- nothing
here touches Google, so it runs offline and costs nothing.

    venv/bin/python3 scripts/test_free_windows.py
"""
import datetime
import os
import sys
import unittest
from unittest import mock
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import gcalendar

DETROIT = ZoneInfo('America/Detroit')


def event(title, start, end, **extra):
    """Shape a get_events row. Times are Detroit-local unless they carry a Z."""
    row = {'title': title, 'start': start, 'end': end, 'calendar': 'Test',
           'all_day': 'T' not in start, 'transparency': 'opaque',
           'declined': False}
    row.update(extra)
    return row


class FreeWindowTests(unittest.TestCase):
    def setUp(self):
        patcher = mock.patch.object(gcalendar, 'LOCAL_TZ', lambda: DETROIT)
        patcher.start()
        self.addCleanup(patcher.stop)
        self.monday = datetime.datetime(2026, 9, 7, 0, 0, tzinfo=DETROIT)
        self.day_start = datetime.time(8, 0)
        self.day_end = datetime.time(22, 0)

    def gaps(self, events, days=1, buffer_minutes=15, earliest=None):
        busy, all_day = gcalendar.busy_intervals(events, buffer_minutes)
        return gcalendar.open_gaps(busy, self.day_start, self.day_end, days,
                                   self.monday, earliest=earliest), all_day

    # -- timezone ----------------------------------------------------------

    def test_utc_calendar_blocks_the_right_local_hours(self):
        """The Family calendar is UTC. 13:00Z is 09:00 Detroit, not 13:00."""
        events = [event('Family thing', '2026-09-07T13:00:00Z',
                        '2026-09-07T14:00:00Z')]
        busy, _ = gcalendar.busy_intervals(events, buffer_minutes=0)
        self.assertEqual(busy[0][0].hour, 9)
        self.assertEqual(busy[0][1].hour, 10)

    def test_offset_events_normalise_before_comparison(self):
        """Two calendars, two offsets, same real hour -- must merge, not stack."""
        events = [
            event('A', '2026-09-07T13:00:00Z', '2026-09-07T14:00:00Z'),
            event('B', '2026-09-07T09:00:00-04:00', '2026-09-07T10:00:00-04:00'),
        ]
        busy, _ = gcalendar.busy_intervals(events, buffer_minutes=0)
        self.assertEqual(len(busy), 1)

    # -- what counts as busy ------------------------------------------------

    def test_all_day_events_do_not_block_and_are_reported(self):
        """33 assignments are loaded as all-day rows. Blocking on them would
        erase the semester."""
        events = [event('PS4 due', '2026-09-07', '2026-09-08')]
        gaps, all_day = self.gaps(events)
        self.assertEqual(len(gaps), 1)
        self.assertEqual(gaps[0][0].hour, 8)
        self.assertEqual(gaps[0][1].hour, 22)
        self.assertEqual(all_day[0]['title'], 'PS4 due')
        self.assertEqual(all_day[0]['date'], '2026-09-07')

    def test_declined_invite_does_not_block(self):
        events = [event('Optional sync', '2026-09-07T10:00:00-04:00',
                        '2026-09-07T11:00:00-04:00', declined=True)]
        gaps, _ = self.gaps(events)
        self.assertEqual(len(gaps), 1)

    def test_transparent_event_does_not_block(self):
        events = [event('Shown as free', '2026-09-07T10:00:00-04:00',
                        '2026-09-07T11:00:00-04:00', transparency='transparent')]
        gaps, _ = self.gaps(events)
        self.assertEqual(len(gaps), 1)

    def test_zero_length_and_inverted_events_are_dropped(self):
        events = [event('Glitch', '2026-09-07T10:00:00-04:00',
                        '2026-09-07T10:00:00-04:00')]
        gaps, _ = self.gaps(events)
        self.assertEqual(len(gaps), 1)

    # -- buffer -------------------------------------------------------------

    def test_buffer_keeps_a_slot_off_the_end_of_a_class(self):
        """A class ending at 09:00 must not yield a 09:00 start."""
        events = [event('EECS 281', '2026-09-07T08:00:00-04:00',
                        '2026-09-07T09:00:00-04:00')]
        gaps, _ = self.gaps(events)
        self.assertEqual(gaps[0][0].strftime('%H:%M'), '09:15')
        slots = gcalendar.slots_in_gap(gaps[0][0], gaps[0][1], 90)
        self.assertEqual(slots[0][0].strftime('%H:%M'), '09:30')

    def test_back_to_back_classes_merge_into_one_blocked_stretch(self):
        events = [
            event('Class A', '2026-09-07T09:00:00-04:00', '2026-09-07T10:00:00-04:00'),
            event('Class B', '2026-09-07T10:00:00-04:00', '2026-09-07T11:00:00-04:00'),
        ]
        busy, _ = gcalendar.busy_intervals(events, buffer_minutes=15)
        self.assertEqual(len(busy), 1)
        self.assertEqual(busy[0][1].strftime('%H:%M'), '11:15')

    # -- day bounds ---------------------------------------------------------

    def test_windows_never_run_overnight(self):
        """22:00 Monday to 08:00 Tuesday is not a study window."""
        gaps, _ = self.gaps([], days=2)
        self.assertEqual(len(gaps), 2)
        for start, end in gaps:
            self.assertEqual(start.strftime('%H:%M'), '08:00')
            self.assertEqual(end.strftime('%H:%M'), '22:00')

    def test_earliest_trims_the_past_and_aligns_forward(self):
        now = datetime.datetime(2026, 9, 7, 14, 3, tzinfo=DETROIT)
        gaps, _ = self.gaps([], earliest=now)
        self.assertEqual(gaps[0][0].strftime('%H:%M'), '14:30')

    def test_fully_booked_day_yields_nothing(self):
        events = [event('All day booked', '2026-09-07T08:00:00-04:00',
                        '2026-09-07T22:00:00-04:00')]
        gaps, _ = self.gaps(events)
        self.assertEqual(gaps, [])

    # -- slot placement -----------------------------------------------------

    def test_gap_shorter_than_the_block_yields_no_slot(self):
        start = datetime.datetime(2026, 9, 7, 13, 0, tzinfo=DETROIT)
        end = start + datetime.timedelta(minutes=60)
        self.assertEqual(gcalendar.slots_in_gap(start, end, 90), [])

    def test_slots_are_capped_per_gap(self):
        start = datetime.datetime(2026, 9, 7, 8, 0, tzinfo=DETROIT)
        end = datetime.datetime(2026, 9, 7, 22, 0, tzinfo=DETROIT)
        slots = gcalendar.slots_in_gap(start, end, 90)
        self.assertEqual(len(slots), gcalendar.MAX_SLOTS_PER_GAP)

    def test_slots_spread_across_the_gap_rather_than_clustering(self):
        """Three options should mean three different times of day."""
        start = datetime.datetime(2026, 9, 7, 8, 0, tzinfo=DETROIT)
        end = datetime.datetime(2026, 9, 7, 22, 0, tzinfo=DETROIT)
        slots = gcalendar.slots_in_gap(start, end, 90)
        self.assertEqual([slot[0].strftime('%H:%M') for slot in slots],
                         ['08:00', '14:00', '20:30'])
        # Last one ends exactly on the bound -- the latest that fits.
        self.assertEqual(slots[-1][1].strftime('%H:%M'), '22:00')

    def test_gap_fitting_exactly_one_block_returns_one_slot(self):
        start = datetime.datetime(2026, 9, 7, 13, 0, tzinfo=DETROIT)
        end = start + datetime.timedelta(minutes=90)
        slots = gcalendar.slots_in_gap(start, end, 90)
        self.assertEqual(len(slots), 1)
        self.assertEqual(slots[0][0].strftime('%H:%M'), '13:00')

    def test_every_slot_stays_inside_its_gap(self):
        """Spreading must never push the last block past the gap end."""
        start = datetime.datetime(2026, 9, 7, 9, 20, tzinfo=DETROIT)
        for minutes in range(90, 600, 10):
            end = start + datetime.timedelta(minutes=minutes)
            for slot_start, slot_end in gcalendar.slots_in_gap(start, end, 90):
                self.assertGreaterEqual(slot_start, start)
                self.assertLessEqual(slot_end, end)

    # -- the refusal --------------------------------------------------------

    def test_a_failed_calendar_refuses_rather_than_reporting_a_free_week(self):
        """The property the whole design is for: an incomplete schedule must
        not produce slots, because a slot could land on a class we can't see."""
        broken = {'failures': [{'calendar': 'Classes', 'error': 'HttpError 403'}],
                  'calendars_found': 4, 'calendars_queried': 3,
                  'window_mode': 'calendar', 'window_start': '', 'window_end': '',
                  'duplicates_collapsed': 0}
        with mock.patch.object(gcalendar, 'get_events', return_value=([], broken)):
            slots, report = gcalendar.free_windows(days=7)
        self.assertEqual(slots, [])
        self.assertIn('refused', report)

    def test_bad_bounds_are_rejected(self):
        with self.assertRaises(ValueError):
            gcalendar.free_windows(day_start='22:00', day_end='08:00')
        with self.assertRaises(ValueError):
            gcalendar.free_windows(day_start='8am', day_end='22:00')


if __name__ == '__main__':
    unittest.main(verbosity=2)
