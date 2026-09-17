"""Provider transport: the seam every later layer calls.

Live and replay are the only two adapters (KTD6). The DeepSeek live adapter and
the fixture adapter that reads U1's captures are not built yet — they need U1's
live capture to exist, because a fixture authored alongside the parser only
proves that the two agree.
"""

from temper_harness.provider.errors import (
    ContentFiltered,
    ContextLengthExceeded,
    EndpointRejected,
    IncompleteStream,
    MalformedResponse,
    MalformedStream,
    PreConnectionUnavailable,
    RateLimited,
    RequestTimeout,
    ServerError,
    ToolSchemaRejected,
    TransportError,
    UnknownTransportError,
    classify_exception,
    for_http_status,
)
from temper_harness.provider.interface import (
    OFFICIAL_HOST,
    BufferedTransport,
    EndpointPolicy,
    Event,
    ReasoningDelta,
    Request,
    Terminal,
    TextDelta,
    ToolCallDelta,
    Transport,
    UsageReported,
    reassemble_tool_calls,
    validate_tool_arguments,
)
from temper_harness.provider.messages import (
    ROLES,
    ChatMessage,
    MessageArrayError,
    ToolCall,
    ToolDefinition,
    build_wire_request,
    validate_messages,
)

__all__ = [
    "OFFICIAL_HOST",
    "ROLES",
    "BufferedTransport",
    "ChatMessage",
    "ContentFiltered",
    "ContextLengthExceeded",
    "EndpointPolicy",
    "EndpointRejected",
    "Event",
    "IncompleteStream",
    "MalformedResponse",
    "MalformedStream",
    "MessageArrayError",
    "PreConnectionUnavailable",
    "RateLimited",
    "ReasoningDelta",
    "Request",
    "RequestTimeout",
    "ServerError",
    "Terminal",
    "TextDelta",
    "ToolCall",
    "ToolCallDelta",
    "ToolDefinition",
    "ToolSchemaRejected",
    "Transport",
    "TransportError",
    "UnknownTransportError",
    "UsageReported",
    "build_wire_request",
    "classify_exception",
    "for_http_status",
    "reassemble_tool_calls",
    "validate_messages",
    "validate_tool_arguments",
]
