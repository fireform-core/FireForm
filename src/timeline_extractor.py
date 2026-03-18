"""
timeline_extractor.py

Incident Timeline Extraction Module for FireForm.

This module extracts chronological events from incident narratives
and returns structured timeline data.

Author: FireForm Contributor
"""

import re
import logging
from datetime import datetime
from dataclasses import dataclass
from typing import List, Optional


logger = logging.getLogger(__name__)


# Precompiled regex patterns
TIME_PATTERN = re.compile(
    r"\b(\d{1,2}:\d{2}\s?(?:AM|PM|am|pm)?|\d{1,2}:\d{2})\b"
)

SENTENCE_SPLIT_PATTERN = re.compile(r"[.!?\n]+")


@dataclass
class TimelineEvent:
    """
    Data model representing a timeline event.
    """
    event: str
    time: str


class TimelineExtractor:
    """
    Extracts chronological timeline events from incident narratives.
    """

    def __init__(self) -> None:
        self.time_pattern = TIME_PATTERN

    def normalize_time(self, time_str: str) -> Optional[str]:
        """
        Normalize time string into 24-hour HH:MM format.
        """
        time_str = time_str.strip()

        formats = [
            "%I:%M %p",
            "%I:%M%p",
            "%H:%M",
        ]

        for fmt in formats:
            try:
                parsed = datetime.strptime(time_str, fmt)
                return parsed.strftime("%H:%M")
            except ValueError:
                continue

        logger.warning(f"Unable to normalize time: {time_str}")
        return None

    def split_sentences(self, text: str) -> List[str]:
        """
        Split narrative into sentences.
        """
        sentences = SENTENCE_SPLIT_PATTERN.split(text)
        return [s.strip() for s in sentences if s.strip()]

    def extract_events(self, text: str) -> List[TimelineEvent]:
        """
        Extract timeline events from narrative text.
        """
        events: List[TimelineEvent] = []

        sentences = self.split_sentences(text)

        for sentence in sentences:

            matches = self.time_pattern.findall(sentence)

            if not matches:
                continue

            for time_match in matches:

                normalized = self.normalize_time(time_match)

                if not normalized:
                    continue

                event_text = sentence.replace(time_match, "").strip()

                event_text = re.sub(r"\s+", " ", event_text)

                if not event_text:
                    continue

                events.append(
                    TimelineEvent(
                        event=event_text,
                        time=normalized
                    )
                )

        return events

    def sort_events(self, events: List[TimelineEvent]) -> List[TimelineEvent]:
        """
        Sort events chronologically.
        """

        def parse_time(event: TimelineEvent):
            try:
                return datetime.strptime(event.time, "%H:%M")
            except Exception:
                return datetime.min

        return sorted(events, key=parse_time)

    def extract_timeline(self, text: str) -> List[dict]:
        """
        Main public API.

        Returns structured timeline data.
        """

        if not text or not isinstance(text, str):
            logger.warning("Invalid input provided to timeline extractor.")
            return []

        try:

            events = self.extract_events(text)

            if not events:
                return []

            sorted_events = self.sort_events(events)

            return [
                {
                    "event": e.event,
                    "time": e.time
                }
                for e in sorted_events
            ]

        except Exception as exc:
            logger.error("Timeline extraction failed.", exc_info=exc)
            return []