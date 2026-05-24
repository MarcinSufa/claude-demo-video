#!/usr/bin/env bash
# Renders Claude-Code-style terminal scenes for VHS.
# Palette is templated by apply-brand.py ({{ansi_*}} placeholders).
# Scene CONTENT (memories, agents, dialogue) is sourced from scene-data.sh.
# Usage: bash display.sh <scene>
#   scene: hero | input | amnesia | recall | agent:<index>

# Source generated content (same dir as this rendered script)
DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck disable=SC1091
source "$DIR/scene-data.sh"

# Palette (true-color ANSI) — substituted by apply-brand.py
ACCENT=$'\e[38;2;{{ansi_accent}}m'
FG=$'\e[38;2;{{ansi_fg}}m'
FG_LO=$'\e[38;2;{{ansi_fg_lo}}m'
FG_FAINT=$'\e[38;2;{{ansi_fg_faint}}m'
RULE=$'\e[38;2;{{ansi_rule}}m'
M_FACT=$'\e[38;2;{{ansi_mem_fact}}m'
M_SKILL=$'\e[38;2;{{ansi_mem_skill}}m'
M_DECISION=$'\e[38;2;{{ansi_mem_decision}}m'
M_PREFERENCE=$'\e[38;2;{{ansi_mem_preference}}m'
M_CONSTRAINT=$'\e[38;2;{{ansi_mem_constraint}}m'
M_CORRECTION=$'\e[38;2;{{ansi_mem_correction}}m'
M_EPISODIC=$'\e[38;2;{{ansi_mem_episodic}}m'
M_TASK=$'\e[38;2;{{ansi_mem_task}}m'
B=$'\e[1m'
R=$'\e[0m'

# Color for a memory type name
mem_color() {
  case "$1" in
    fact) printf '%s' "$M_FACT" ;;
    skill) printf '%s' "$M_SKILL" ;;
    decision) printf '%s' "$M_DECISION" ;;
    preference|pref) printf '%s' "$M_PREFERENCE" ;;
    constraint) printf '%s' "$M_CONSTRAINT" ;;
    correction) printf '%s' "$M_CORRECTION" ;;
    episodic) printf '%s' "$M_EPISODIC" ;;
    task|project) printf '%s' "$M_TASK" ;;
    *) printf '%s' "$FG" ;;
  esac
}

header() {
  printf '\n  %s▦%s  %s%s%s\n' "$ACCENT" "$R" "$B" "$CLI_NAME" "$R"
  printf '      %s%s · %s%s\n' "$FG_FAINT" "$CLI_SUBTITLE" "$WORKDIR" "$R"
}

divider() {
  printf '\n  %s─────────────────────────────────────────────────────%s\n' "$RULE" "$R"
}

# Print the recall memory list (used by recall + agent scenes)
print_memories() {
  local i
  for i in "${!MEM_TYPES[@]}"; do
    local t="${MEM_TYPES[$i]}"
    local c; c="$(mem_color "$t")"
    printf '  %s%-11s%s %s\n' "$c" "$t" "$R" "${MEM_TEXTS[$i]}"
  done
}

wait_for_input() { exec bash --noprofile --norc -c 'IFS= read -r _ ; sleep 30'; }

case "$1" in
  hero)
    clear; header
    printf '      %s%s/src%s\n' "$FG_FAINT" "$WORKDIR" "$R"
    printf '\n\n\n\n\n\n\n'; divider; printf '  > '; sleep 30 ;;
  input)
    clear; header
    printf '\n\n\n\n'; divider; printf '  > '; wait_for_input ;;
  amnesia)
    clear; header
    printf '\n  %s›%s %s\n' "$FG_LO" "$R" "$AMNESIA_USER"
    printf '\n  %s%s%s\n' "$FG_LO" "$AMNESIA_REPLY1" "$R"
    [ -n "$AMNESIA_REPLY2" ] && printf '  %s%s%s\n' "$FG_LO" "$AMNESIA_REPLY2" "$R"
    divider; printf '  > '; wait_for_input ;;
  recall)
    clear; header
    printf '\n\n\n\n\n'; divider; printf '  > '; sleep 1.5
    clear; header
    printf '\n  %s◐ %s%s %srecalling session context...%s\n' "$ACCENT" "$PRODUCT" "$R" "$FG_LO" "$R"
    printf '\n\n\n'; divider; printf '  > '; sleep 1.2
    clear; header
    printf '\n  %s◐ %s%s %s· %d memories · graph traversed in 0.04s%s\n\n' "$ACCENT" "$PRODUCT" "$R" "$FG_LO" "${#MEM_TYPES[@]}" "$R"
    print_memories
    divider; printf '  > '; wait_for_input ;;
  agent:*)
    idx="${1#agent:}"
    clear
    printf '\n  %s%s%s  %s%s%s\n' "$ACCENT" "${AGENT_SIGILS[$idx]}" "$R" "$B" "${AGENT_NAMES[$idx]}" "$R"
    printf '      %s%s · %s%s\n' "$FG_FAINT" "${AGENT_SUBS[$idx]}" "$WORKDIR" "$R"
    printf '\n  %s◐ %s%s %s· %d memories%s\n\n' "$ACCENT" "$PRODUCT" "$R" "$FG_LO" "${#MEM_TYPES[@]}" "$R"
    print_memories
    divider; printf '  > '; sleep 30 ;;
  *)
    echo "Unknown scene: $1" >&2
    echo "Use: hero | input | amnesia | recall | agent:<index>" >&2
    exit 1 ;;
esac
