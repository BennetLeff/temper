#!/bin/bash

# dispatch_core.sh
# Usage: ./tools/agents/dispatch_core.sh <agent_role> <model_tier> "<instruction>" <output_file>

ROLE=$1
TIER=$2
INSTRUCTION=$3
OUTPUT_FILE=$4

# Define model based on tier
if [ "$TIER" == "thinking" ]; then
  # Use Gemini 3 Pro model for reasoning-heavy tasks
  GEMINI_MODEL="gemini-3-pro-preview" 
  echo "🧠 Using Thinking Model ($GEMINI_MODEL) for $ROLE..."
else
  # Use Gemini 3 Flash model for speed/volume
  GEMINI_MODEL="gemini-3-flash-preview"
  echo "⚡ Using Fast Model ($GEMINI_MODEL) for $ROLE..."
fi

# Define system prompts for different roles
case $ROLE in
  "architect")
    SYSTEM_CONTEXT="You are a Senior System Architect. Focus on high-level design, patterns, and scalability. Think deeply about trade-offs."
    ;;
  "security")
    SYSTEM_CONTEXT="You are a Security Specialist. Focus on identifying vulnerabilities, input validation, and secure coding practices. Be paranoid."
    ;;
  "tester")
    SYSTEM_CONTEXT="You are a QA Engineer. Focus on edge cases, test coverage, and breaking the code."
    ;;
  "coder")
    SYSTEM_CONTEXT="You are a Python Expert. Focus on writing clean, efficient, and typed code."
    ;;
  *)
    SYSTEM_CONTEXT="You are a helpful assistant."
    ;;
esac

# Construct the prompt
FULL_PROMPT="$SYSTEM_CONTEXT\n\nTask: $INSTRUCTION\n\nPlease write your response to the file '$OUTPUT_FILE'."

# Invoke the CLI
# -m: Specify model
# -y: YOLO mode (auto-approve tools) so it runs non-interactively
# "$FULL_PROMPT": The instruction
gemini -m "$GEMINI_MODEL" -y "$FULL_PROMPT" > "$OUTPUT_FILE"

echo "Agent $ROLE completed task. Output saved to $OUTPUT_FILE"
