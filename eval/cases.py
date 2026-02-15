"""All test case definitions across 8 categories (40 total)."""

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
    # For no_extra_tools check: fail if tools outside this set are called
    forbidden_tools: list[str] | None = None


# ---------------------------------------------------------------------------
# Category: tool_selection (10 cases)
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
    # --- New harder cases ---
    TestCase(
        id="ts_08",
        category="tool_selection",
        prompt="Do I have anything going on this weekend?",
        expected_tools=["list_calendar_events"],
    ),
    TestCase(
        id="ts_09",
        category="tool_selection",
        prompt="Find me a good Italian restaurant near campus.",
        expected_tools=["web_search"],
        required_args={"web_search": ["query"]},
    ),
    TestCase(
        id="ts_10",
        category="tool_selection",
        prompt="Block off next Friday afternoon for studying — 1pm to 5pm.",
        expected_tools=["create_calendar_event"],
        required_args={"create_calendar_event": ["summary", "start", "end"]},
    ),
]

# ---------------------------------------------------------------------------
# Category: multi_step (5 cases)
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
    # --- New ---
    TestCase(
        id="ms_04",
        category="multi_step",
        prompt="Push my team standup back by 30 minutes.",
        expected_tools=["list_calendar_events", "update_calendar_event"],
        expected_tool_sequence=["list_calendar_events", "update_calendar_event"],
        required_args={"update_calendar_event": ["event_id", "start", "end"]},
    ),
    TestCase(
        id="ms_05",
        category="multi_step",
        prompt="Add a note to my dentist appointment: 'Bring insurance card'.",
        expected_tools=["list_calendar_events", "update_calendar_event"],
        expected_tool_sequence=["list_calendar_events", "update_calendar_event"],
        required_args={"update_calendar_event": ["event_id", "description"]},
    ),
]

# ---------------------------------------------------------------------------
# Category: no_tool (7 cases)
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
    # --- New ---
    TestCase(
        id="nt_06",
        category="no_tool",
        prompt="What does RSVP stand for?",
        expected_tools=[],
        expected_content=["répondez"],
    ),
    TestCase(
        id="nt_07",
        category="no_tool",
        prompt="Convert 72°F to Celsius.",
        expected_tools=[],
        expected_content=["22"],
    ),
]

# ---------------------------------------------------------------------------
# Category: arg_quality (6 cases)
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
    # --- New ---
    TestCase(
        id="aq_05",
        category="arg_quality",
        prompt="Create a 45-minute event called 'Coffee Chat' at 10:15 AM on February 19th.",
        expected_tools=["create_calendar_event"],
        required_args={"create_calendar_event": ["summary", "start", "end"]},
        check_iso_dates=True,
        check_timezone_offset=True,
    ),
    TestCase(
        id="aq_06",
        category="arg_quality",
        prompt="Schedule 'Flight to NYC' on March 1st from 6:00 AM to 8:30 AM.",
        expected_tools=["create_calendar_event"],
        required_args={"create_calendar_event": ["summary", "start", "end"]},
        check_iso_dates=True,
        check_timezone_offset=True,
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
# Category: response_quality (5 cases)
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
        expected_content=["dentist"],
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
    # --- New ---
    TestCase(
        id="rq_04",
        category="response_quality",
        prompt="How many events do I have in the next week?",
        expected_tools=["list_calendar_events"],
        expected_content=["3"],
        max_words=40,
    ),
    TestCase(
        id="rq_05",
        category="response_quality",
        prompt="Give me a one-line summary of my week.",
        expected_tools=["list_calendar_events"],
        max_words=50,
    ),
]

# ---------------------------------------------------------------------------
# Category: ambiguity (3 cases) — NEW
# Tests whether the model handles ambiguous or tricky requests correctly.
# ---------------------------------------------------------------------------

AMBIGUITY = [
    TestCase(
        id="am_01",
        category="ambiguity",
        prompt="Cancel my meeting tomorrow.",
        # Should list events first to identify which one — but we don't have a delete tool,
        # so the model should list events and then explain it can't delete.
        expected_tools=["list_calendar_events"],
    ),
    TestCase(
        id="am_02",
        category="ambiguity",
        prompt="What's the weather?",
        # Should use web_search, not get_current_datetime
        expected_tools=["web_search"],
        forbidden_tools=["get_current_datetime"],
    ),
    TestCase(
        id="am_03",
        category="ambiguity",
        prompt="Am I free at 2pm on Tuesday?",
        # Should check calendar, not just guess
        expected_tools=["list_calendar_events"],
    ),
]

# ---------------------------------------------------------------------------
# Category: instruction_following (3 cases) — NEW
# Tests whether the model follows specific formatting/behavioral instructions.
# ---------------------------------------------------------------------------

INSTRUCTION_FOLLOWING = [
    TestCase(
        id="if_01",
        category="instruction_following",
        prompt="List my events tomorrow. Use bullet points.",
        expected_tools=["list_calendar_events"],
        expected_content=["•", "-", "*"],  # any bullet style
        max_words=120,
    ),
    TestCase(
        id="if_02",
        category="instruction_following",
        prompt="What day of the week is February 20th, 2026? Answer in exactly one word.",
        expected_tools=[],
        expected_content=["friday"],
        max_words=5,
    ),
    TestCase(
        id="if_03",
        category="instruction_following",
        prompt="Search for 'Python asyncio tutorial' and tell me the top result title only.",
        expected_tools=["web_search"],
        max_words=30,
    ),
]


ALL_CASES = (
    TOOL_SELECTION + MULTI_STEP + NO_TOOL + ARG_QUALITY +
    VISION + RESPONSE_QUALITY + AMBIGUITY + INSTRUCTION_FOLLOWING
)

CATEGORIES = {
    "tool_selection": TOOL_SELECTION,
    "multi_step": MULTI_STEP,
    "no_tool": NO_TOOL,
    "arg_quality": ARG_QUALITY,
    "vision": VISION,
    "response_quality": RESPONSE_QUALITY,
    "ambiguity": AMBIGUITY,
    "instruction_following": INSTRUCTION_FOLLOWING,
}
