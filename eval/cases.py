"""All 23 test case definitions across 6 categories."""

from dataclasses import dataclass, field


@dataclass
class TestCase:
    id: str
    category: str
    prompt: str
    expected_tools: list[str] = field(default_factory=list)
    required_args: dict[str, list[str]] = field(default_factory=dict)
    expected_tool_sequence: list[str] | None = None
    expected_content: list[str] = field(default_factory=list)
    max_words: int | None = None
    image_b64: str | None = None
    check_iso_dates: bool = False
    check_timezone_offset: bool = False


# ---------------------------------------------------------------------------
# Category: tool_selection (7 cases)
# Tests whether the model picks the right tool for the request.
# ---------------------------------------------------------------------------

TOOL_SELECTION = [
    TestCase(
        id="ts_01",
        category="tool_selection",
        prompt="What's on my calendar this week?",
        expected_tools=["list_calendar_events"],
    ),
    TestCase(
        id="ts_02",
        category="tool_selection",
        prompt="Create a meeting called 'Project Review' tomorrow at 2pm for one hour.",
        expected_tools=["create_calendar_event"],
        required_args={"create_calendar_event": ["summary", "start", "end"]},
    ),
    TestCase(
        id="ts_03",
        category="tool_selection",
        prompt="Search the web for the weather in Toronto today.",
        expected_tools=["web_search"],
        required_args={"web_search": ["query"]},
    ),
    TestCase(
        id="ts_04",
        category="tool_selection",
        prompt="What time is it right now?",
        expected_tools=["get_current_datetime"],
    ),
    TestCase(
        id="ts_05",
        category="tool_selection",
        prompt="Look up who won the Super Bowl this year.",
        expected_tools=["web_search"],
        required_args={"web_search": ["query"]},
    ),
    TestCase(
        id="ts_06",
        category="tool_selection",
        prompt="Add a dentist appointment on February 20th at 3pm, lasting 1 hour.",
        expected_tools=["create_calendar_event"],
        required_args={"create_calendar_event": ["summary", "start", "end"]},
    ),
    TestCase(
        id="ts_07",
        category="tool_selection",
        prompt="Show me my schedule for the next 3 days.",
        expected_tools=["list_calendar_events"],
    ),
]

# ---------------------------------------------------------------------------
# Category: multi_step (3 cases)
# Tests chaining tools: must list events first, then update.
# ---------------------------------------------------------------------------

MULTI_STEP = [
    TestCase(
        id="ms_01",
        category="multi_step",
        prompt="Move my team standup to 10am tomorrow.",
        expected_tools=["list_calendar_events", "update_calendar_event"],
        expected_tool_sequence=["list_calendar_events", "update_calendar_event"],
        required_args={"update_calendar_event": ["event_id"]},
    ),
    TestCase(
        id="ms_02",
        category="multi_step",
        prompt="Change the location of my dentist appointment to '456 Oak Ave'.",
        expected_tools=["list_calendar_events", "update_calendar_event"],
        expected_tool_sequence=["list_calendar_events", "update_calendar_event"],
        required_args={"update_calendar_event": ["event_id", "location"]},
    ),
    TestCase(
        id="ms_03",
        category="multi_step",
        prompt="Rename my lunch with Sarah to 'Lunch with Sarah and Mike'.",
        expected_tools=["list_calendar_events", "update_calendar_event"],
        expected_tool_sequence=["list_calendar_events", "update_calendar_event"],
        required_args={"update_calendar_event": ["event_id", "summary"]},
    ),
]

# ---------------------------------------------------------------------------
# Category: no_tool (5 cases)
# Model should respond directly without calling any tools.
# ---------------------------------------------------------------------------

NO_TOOL = [
    TestCase(
        id="nt_01",
        category="no_tool",
        prompt="What is the capital of France?",
        expected_tools=[],
        expected_content=["paris"],
    ),
    TestCase(
        id="nt_02",
        category="no_tool",
        prompt="Explain what a binary search is in one sentence.",
        expected_tools=[],
        max_words=60,
    ),
    TestCase(
        id="nt_03",
        category="no_tool",
        prompt="Say hello!",
        expected_tools=[],
    ),
    TestCase(
        id="nt_04",
        category="no_tool",
        prompt="What's 15 * 23?",
        expected_tools=[],
        expected_content=["345"],
    ),
    TestCase(
        id="nt_05",
        category="no_tool",
        prompt="Translate 'good morning' to French.",
        expected_tools=[],
        expected_content=["bonjour"],
    ),
]

# ---------------------------------------------------------------------------
# Category: arg_quality (4 cases)
# Tests ISO 8601 dates, timezone offsets, and valid arguments.
# ---------------------------------------------------------------------------

ARG_QUALITY = [
    TestCase(
        id="aq_01",
        category="arg_quality",
        prompt="Schedule a meeting called 'Sprint Planning' on February 18th at 9am for 2 hours.",
        expected_tools=["create_calendar_event"],
        required_args={"create_calendar_event": ["summary", "start", "end"]},
        check_iso_dates=True,
        check_timezone_offset=True,
    ),
    TestCase(
        id="aq_02",
        category="arg_quality",
        prompt="Create an event 'Doctor Visit' on February 20, 2026 from 2:30 PM to 3:30 PM.",
        expected_tools=["create_calendar_event"],
        required_args={"create_calendar_event": ["summary", "start", "end"]},
        check_iso_dates=True,
        check_timezone_offset=True,
    ),
    TestCase(
        id="aq_03",
        category="arg_quality",
        prompt="Add 'Team Dinner' to my calendar on February 21st from 6pm to 9pm at 'The Keg Steakhouse'.",
        expected_tools=["create_calendar_event"],
        required_args={"create_calendar_event": ["summary", "start", "end"]},
        check_iso_dates=True,
    ),
    TestCase(
        id="aq_04",
        category="arg_quality",
        prompt="Check my calendar for the next 14 days.",
        expected_tools=["list_calendar_events"],
        required_args={"list_calendar_events": ["days"]},
    ),
]

# ---------------------------------------------------------------------------
# Category: vision (1 case)
# Tests image understanding with a programmatically generated test image.
# ---------------------------------------------------------------------------

VISION = [
    TestCase(
        id="vis_01",
        category="vision",
        prompt="Describe what you see in this image.",
        expected_tools=[],
        expected_content=["red", "blue"],
        image_b64="DEFERRED",  # filled in at runtime by runner
    ),
]

# ---------------------------------------------------------------------------
# Category: response_quality (3 cases)
# Tests conciseness and correct information extraction from tool results.
# ---------------------------------------------------------------------------

RESPONSE_QUALITY = [
    TestCase(
        id="rq_01",
        category="response_quality",
        prompt="What's on my calendar tomorrow? Keep it brief.",
        expected_tools=["list_calendar_events"],
        expected_content=["standup", "lunch", "sarah"],
        max_words=100,
    ),
    TestCase(
        id="rq_02",
        category="response_quality",
        prompt="When is my dentist appointment?",
        expected_tools=["list_calendar_events"],
        expected_content=["dentist", "february 17"],
        max_words=60,
    ),
    TestCase(
        id="rq_03",
        category="response_quality",
        prompt="Where is my lunch tomorrow?",
        expected_tools=["list_calendar_events"],
        expected_content=["café roma"],
        max_words=40,
    ),
]


ALL_CASES = TOOL_SELECTION + MULTI_STEP + NO_TOOL + ARG_QUALITY + VISION + RESPONSE_QUALITY

CATEGORIES = {
    "tool_selection": TOOL_SELECTION,
    "multi_step": MULTI_STEP,
    "no_tool": NO_TOOL,
    "arg_quality": ARG_QUALITY,
    "vision": VISION,
    "response_quality": RESPONSE_QUALITY,
}
