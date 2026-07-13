#!/usr/bin/env bash
# Temper Onboard Script — guided quick-start achievement run
# Invoked via: make onboard | make onboard-status
# macOS bash 3.2+ compatible — no associative arrays, no bashisms >4.x

set -u
set -o pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
ONBOARD_DIR="${REPO_ROOT}/.onboard"
RESULTS_FILE="${ONBOARD_DIR}/results.txt"
RESULT_SEP="|||"

# ── ANSI colours ────────────────────────────────────────────────────────────

if [ -t 1 ]; then
	GREEN='\033[32m'; RED='\033[31m'; YELLOW='\033[33m'
	CYAN='\033[36m'; BOLD='\033[1m'; DIM='\033[2m'; RESET='\033[0m'
else
	GREEN='' RED='' YELLOW='' CYAN='' BOLD='' DIM='' RESET=''
fi

# ── Terminal width ──────────────────────────────────────────────────────────

detect_term_width() {
	local w="${COLUMNS:-80}"
	if [ "$w" -lt 70 ]; then w=70; fi
	if [ "$w" -gt 140 ]; then w=140; fi
	echo "$w"
}

# ── Git HEAD helper ─────────────────────────────────────────────────────────

git_head() {
	if command -v git >/dev/null 2>&1 && git -C "$REPO_ROOT" rev-parse --git-dir >/dev/null 2>&1; then
		git -C "$REPO_ROOT" rev-parse HEAD 2>/dev/null || echo "no-git-head"
	else
		echo "no-git-head"
	fi
}

# ── Checkpoint helpers ──────────────────────────────────────────────────────

checkpoint_is_valid() {
	local stage="$1"
	local marker="${ONBOARD_DIR}/${stage}.ok"
	local current
	current="$(git_head)"
	if [ -f "$marker" ]; then
		local recorded
		recorded="$(cat "$marker")"
		if [ "$current" = "$recorded" ] && [ "$current" != "no-git-head" ]; then
			return 0
		else
			if [ "$current" != "$recorded" ]; then
				echo "  ${DIM}[INFO]${RESET} ${stage} — code changed, re-running"
			fi
		fi
	fi
	return 1
}

checkpoint_write() {
	local stage="$1"
	mkdir -p "$ONBOARD_DIR"
	git_head > "${ONBOARD_DIR}/${stage}.ok"
}

checkpoint_cascade_clear() {
	local stages_after=("$@")
	for s in "${stages_after[@]}"; do
		rm -f "${ONBOARD_DIR}/${s}.ok"
	done
}

# ── Result tracking (flat file: stage|||status|||detail) ────────────────────

result_write() {
	local stage="$1" status="$2" detail="$3"
	mkdir -p "$ONBOARD_DIR"
	# Remove any previous line for this stage
	if [ -f "$RESULTS_FILE" ]; then
		grep -v "^${stage}${RESULT_SEP}" "$RESULTS_FILE" > "${RESULTS_FILE}.tmp" 2>/dev/null || true
		mv "${RESULTS_FILE}.tmp" "$RESULTS_FILE" 2>/dev/null || rm -f "$RESULTS_FILE"
	fi
	# If RESULTS_FILE is empty or not there, create it
	if [ ! -f "$RESULTS_FILE" ] || [ ! -s "$RESULTS_FILE" ]; then
		printf '%s%s%s%s%s\n' "$stage" "$RESULT_SEP" "$status" "$RESULT_SEP" "$detail" > "$RESULTS_FILE"
	else
		printf '%s%s%s%s%s\n' "$stage" "$RESULT_SEP" "$status" "$RESULT_SEP" "$detail" >> "$RESULTS_FILE"
	fi
}

result_get() {
	local stage="$1"
	if [ -f "$RESULTS_FILE" ]; then
		grep "^${stage}${RESULT_SEP}" "$RESULTS_FILE" 2>/dev/null | head -1 || echo ""
	else
		echo ""
	fi
}

result_get_field() {
	local stage="$1" field="$2"
	local line
	line="$(result_get "$stage")"
	if [ -n "$line" ]; then
		echo "$line" | cut -d"$RESULT_SEP" -f"$field"
	fi
}

# ── Banner rendering ────────────────────────────────────────────────────────

print_banner() {
	local icon="$1" name="$2" detail="$3"
	local w
	w="$(detect_term_width)"
	local inner_w=$((w - 2))
	local header="${icon} ${name}"

	printf '\n'
	printf '%s' "${BOLD}${CYAN}"
	# top border
	printf '\342\224\214'  # ┌
	local i
	for i in $(seq 1 $inner_w); do printf '\342\224\200'; done  # ─
	printf '\342\224\220\n'  # ┐

	# title line
	printf '\342\224\202'  # │
	local pad_left=$(( (inner_w - ${#header}) / 2 ))
	local pad_right=$(( inner_w - ${#header} - pad_left ))
	for i in $(seq 1 $pad_left); do printf ' '; done
	printf '%s' "${header}"
	for i in $(seq 1 $pad_right); do printf ' '; done
	printf '\342\224\202\n'  # │

	# detail line (if present)
	if [ -n "$detail" ]; then
		printf '\342\224\202'  # │
		local dtext="${DIM}${detail}${RESET}${BOLD}${CYAN}"
		# strip ANSI for length calc
		local dtext_plain="${detail}"
		local dpad=$(( (inner_w - ${#dtext_plain} - 2) / 2 ))
		[ "$dpad" -lt 0 ] && dpad=0
		for i in $(seq 1 $dpad); do printf ' '; done
		printf ' %s ' "$detail"
		local dremain=$(( inner_w - ${#dtext_plain} - 2 - dpad ))
		[ "$dremain" -lt 0 ] && dremain=0
		for i in $(seq 1 $dremain); do printf ' '; done
		printf '\342\224\202\n'  # │
	fi

	# bottom border
	printf '\342\224\224'  # └
	for i in $(seq 1 $inner_w); do printf '\342\224\200'; done  # ─
	printf '\342\224\230\n'  # ┘
	printf '%s' "${RESET}"
	printf '\n'
}

# ── Summary card ────────────────────────────────────────────────────────────

render_summary() {
	printf '\n'
	local w
	w="$(detect_term_width)"
	local inner_w=$((w - 2))

	local pass_str="PASS"
	local fail_str="FAIL"
	local skip_str="SKIP"
	if [ -t 1 ]; then
		pass_str="${GREEN}PASS${RESET}"
		fail_str="${RED}FAIL${RESET}"
		skip_str="${YELLOW}SKIP${RESET}"
	fi

	# Top border
	printf '%s' "${BOLD}${CYAN}"
	printf '\342\224\214'  # ┌
	local i; for i in $(seq 1 $inner_w); do printf '\342\224\200'; done
	printf '\342\224\220\n'  # ┐

	# Title
	local title=" make onboard — Summary "
	printf '\342\224\202'  # │
	local tpad=$(( (inner_w - ${#title}) / 2 ))
	for i in $(seq 1 $tpad); do printf ' '; done
	printf '%s' "$title"
	local tremain=$(( inner_w - ${#title} - tpad ))
	for i in $(seq 1 $tremain); do printf ' '; done
	printf '\342\224\202\n'

	# Separator
	printf '\342\224\234'  # ├
	local col1_w=30
	local col2_w=8
	local col3_w=$(( inner_w - col1_w - col2_w - 4 ))
	for i in $(seq 1 $col1_w); do printf '\342\224\200'; done
	printf '\342\224\274'  # ┼
	for i in $(seq 1 $col2_w); do printf '\342\224\200'; done
	printf '\342\224\274'  # ┼
	for i in $(seq 1 $col3_w); do printf '\342\224\200'; done
	printf '\342\224\244\n'  # ┤

	# Header row
	printf '\342\224\202'  # │
	printf ' %-*s ' $((col1_w - 2)) "Stage"
	printf '\342\224\202'  # │
	printf ' %-*s ' $((col2_w - 2)) "Status"
	printf '\342\224\202'  # │
	printf ' %-*s ' $((col3_w - 2)) "Detail"
	printf '\342\224\202\n'  # │

	# Separator
	printf '\342\224\234'  # ├
	for i in $(seq 1 $col1_w); do printf '\342\224\200'; done
	printf '\342\224\274'  # ┼
	for i in $(seq 1 $col2_w); do printf '\342\224\200'; done
	printf '\342\224\274'  # ┼
	for i in $(seq 1 $col3_w); do printf '\342\224\200'; done
	printf '\342\224\244\n'  # ┤

	# Stage rows (summary-card visible stages)
	local summary_stages="platform-detect toolchain-verify host-test-build host-test-run idf-verify firmware-build flash"
	local s
	for s in $summary_stages; do
		local status_str="   " detail_str=""
		local line
		line="$(result_get "$s")"
		if [ -n "$line" ]; then
			local st
			st="$(echo "$line" | cut -d"$RESULT_SEP" -f2)"
			local dt
			dt="$(echo "$line" | cut -d"$RESULT_SEP" -f3-)"
			case "$st" in
				pass) status_str=" $pass_str " ;;
				fail) status_str=" $fail_str " ;;
				skip) status_str=" $skip_str " ;;
				*)    status_str="  -  " ;;
			esac
			detail_str="$dt"
		else
			status_str="  -  "
			detail_str="not run"
		fi

		local label=""
		case "$s" in
			platform-detect)   label="Platform Detection" ;;
			toolchain-verify)  label="Toolchain Verification" ;;
			host-test-build)   label="Firmware Host Test Build" ;;
			host-test-run)     label="Firmware Host Test Run" ;;
			idf-verify)        label="ESP-IDF Verification" ;;
			firmware-build)    label="Firmware Target Build" ;;
			flash)             label="ESP32-S3 Flash" ;;
		esac

		printf '\342\224\202'  # │
		printf ' %-*s ' $((col1_w - 2)) "$label"
		printf '\342\224\202'  # │
		if [ -t 1 ]; then
			printf ' %b ' "$status_str"
			# pad after ANSI codes (crude but works for short status)
			local raw_len
			case "$st" in
				pass) raw_len=4 ;;
				fail) raw_len=4 ;;
				skip) raw_len=4 ;;
				*)    raw_len=1 ;;
			esac
			local sp=$((col2_w - 2 - raw_len))
			[ "$sp" -lt 0 ] && sp=0
			for i in $(seq 1 $sp); do printf ' '; done
		else
			printf ' %-*s ' $((col2_w - 2)) "$(echo "$status_str" | tr -d ' ') "
		fi
		printf '\342\224\202'  # │
		printf ' %-*s ' $((col3_w - 2)) "${detail_str:0:$((col3_w - 2))}"
		printf '\342\224\202\n'  # │
	done

	# Bottom border
	printf '\342\224\224'  # └
	for i in $(seq 1 $inner_w); do printf '\342\224\200'; done
	printf '\342\224\230\n'  # ┘
	printf '%s' "${RESET}"
	printf '\n'
}

# ── Helper: installation table ──────────────────────────────────────────────

install_hint() {
	local tool="$1" os="$2"
	case "$tool" in
		cmake)
			if [ "$os" = "Darwin" ]; then echo "brew install cmake"
			else echo "apt install cmake"; fi ;;
		gcc|cc)
			if [ "$os" = "Darwin" ]; then echo "xcode-select --install  # or: brew install gcc"
			else echo "apt install build-essential"; fi ;;
		python3)
			if [ "$os" = "Darwin" ]; then echo "brew install python3"
			else echo "apt install python3"; fi ;;
		ctest)
			if [ "$os" = "Darwin" ]; then echo "brew install cmake  # ctest is bundled with cmake"
			else echo "apt install cmake  # ctest is bundled with cmake"; fi ;;
		*) echo "check your package manager" ;;
	esac
}

# ── Stage: Platform Detection ───────────────────────────────────────────────

run_platform_detect() {
	local stage="platform-detect"
	if checkpoint_is_valid "$stage"; then
		result_write "$stage" "pass" "$(result_get_field "$stage" 3)"
		return 0
	fi

	local os
	os="$(uname -s)"
	local pkg=""
	case "$os" in
		Darwin) pkg="brew" ;;
		Linux)  pkg="apt" ;;
		*)      pkg="unknown" ;;
	esac

	if [ "$pkg" = "unknown" ]; then
		echo "  ${YELLOW}[WARN]${RESET} Unsupported platform: ${os}. Continuing optimistically."
		print_banner "???" "Platform Detection" "${os} (unsupported)"
		result_write "$stage" "pass" "${os} (unsupported)"
		checkpoint_write "$stage"
		return 0
	fi

	print_banner "???" "Platform Detection" "${os} — package manager: ${pkg}"
	result_write "$stage" "pass" "${os} — pkg: ${pkg}"
	checkpoint_write "$stage"
	return 0
}

# ── Stage: Toolchain Verification ───────────────────────────────────────────

run_toolchain_verify() {
	local stage="toolchain-verify"
	if checkpoint_is_valid "$stage"; then
		result_write "$stage" "pass" "$(result_get_field "$stage" 3)"
		return 0
	fi

	local os
	os="$(uname -s)"
	local all_ok=1
	local found_list=""
	local missing_list=""
	local tools="cmake gcc python3 ctest"

	for tool in $tools; do
		if command -v "$tool" >/dev/null 2>&1; then
			found_list="${found_list}${tool} "
		else
			# gcc fallback: try cc
			if [ "$tool" = "gcc" ] && command -v cc >/dev/null 2>&1; then
				found_list="${found_list}cc(gcc) "
			else
				local hint
				hint="$(install_hint "$tool" "$os")"
				printf '  %b[FAIL]%b %s — not found. Install: %s\n' "$RED" "$RESET" "$tool" "$hint"
				missing_list="${missing_list}${tool} "
				all_ok=0
			fi
		fi
	done

	if [ "$all_ok" -eq 1 ]; then
		local detail
		detail="${found_list}ok"
		print_banner "???" "Toolchain Verified" "${detail}"
		result_write "$stage" "pass" "${detail}"
		checkpoint_write "$stage"
		return 0
	else
		local detail
		detail="missing: ${missing_list}"
		printf '  %b[FAIL]%b Toolchain incomplete: %s\n' "$RED" "$RESET" "$missing_list"
		result_write "$stage" "fail" "${detail}"
		return 1
	fi
}

# ── Stage: Firmware Host Test Build ─────────────────────────────────────────

run_host_test_build() {
	local stage="host-test-build"
	if checkpoint_is_valid "$stage"; then
		result_write "$stage" "pass" "$(result_get_field "$stage" 3)"
		return 0
	fi

	# Dependency check: toolchain must have cmake and gcc
	local tc_line
	tc_line="$(result_get "toolchain-verify")"
	if [ -z "$tc_line" ]; then
		result_write "$stage" "skip" "toolchain not verified yet"
		return 0
	fi
	local tc_status
	tc_status="$(echo "$tc_line" | cut -d"$RESULT_SEP" -f2)"
	if [ "$tc_status" != "pass" ]; then
		local tc_detail
		tc_detail="$(echo "$tc_line" | cut -d"$RESULT_SEP" -f3-)"
		result_write "$stage" "skip" "toolchain check failed (${tc_detail})"
		return 0
	fi

	if ! command -v cmake >/dev/null 2>&1; then
		result_write "$stage" "skip" "cmake not available"
		return 0
	fi
	if ! command -v gcc >/dev/null 2>&1 && ! command -v cc >/dev/null 2>&1; then
		result_write "$stage" "skip" "no C compiler available"
		return 0
	fi

	printf '  Building firmware host tests...\n'
	local cmake_out cmake_rc build_out build_rc
	cmake_out="$(cmake -B "$TEST_BUILD_DIR" "$TEST_SRC_DIR" 2>&1)" && cmake_rc=$? || cmake_rc=$?
	if [ "$cmake_rc" -ne 0 ]; then
		printf '  %b[FAIL]%b cmake configure failed:\n' "$RED" "$RESET"
		printf '%s\n' "$cmake_out" | tail -20
		printf '  Check %s\n' "${TEST_SRC_DIR}/CMakeLists.txt"
		result_write "$stage" "fail" "cmake configure failed"
		return 1
	fi

	build_out="$(cmake --build "$TEST_BUILD_DIR" 2>&1)" && build_rc=$? || build_rc=$?
	if [ "$build_rc" -ne 0 ]; then
		printf '  %b[FAIL]%b cmake build failed:\n' "$RED" "$RESET"
		printf '%s\n' "$build_out" | tail -20
		result_write "$stage" "fail" "cmake build failed"
		return 1
	fi

	local errors=0 warnings=0
	if echo "$build_out" | grep -qi "error"; then
		errors=$(echo "$build_out" | grep -ci "error" || echo 0)
	fi
	if echo "$build_out" | grep -qi "warning"; then
		warnings=$(echo "$build_out" | grep -ci "warning" || echo 0)
	fi

	local detail
	detail="${errors} errors, ${warnings} warnings"
	if [ "$errors" -eq 0 ]; then
		print_banner "???" "Host Test Build" "${detail}"
		result_write "$stage" "pass" "${detail}"
		checkpoint_write "$stage"
		return 0
	else
		printf '  %b[FAIL]%b Host test build: %s\n' "$RED" "$RESET" "$detail"
		result_write "$stage" "fail" "${detail}"
		return 1
	fi
}

# ── Stage: Firmware Host Test Run ───────────────────────────────────────────

run_host_test_run() {
	local stage="host-test-run"
	if checkpoint_is_valid "$stage"; then
		result_write "$stage" "pass" "$(result_get_field "$stage" 3)"
		return 0
	fi

	# Dependency: host-test-build must pass
	local htb_line
	htb_line="$(result_get "host-test-build")"
	if [ -z "$htb_line" ]; then
		result_write "$stage" "skip" "host test build not done yet"
		return 0
	fi
	local htb_status
	htb_status="$(echo "$htb_line" | cut -d"$RESULT_SEP" -f2)"
	if [ "$htb_status" != "pass" ]; then
		local htb_detail
		htb_detail="$(echo "$htb_line" | cut -d"$RESULT_SEP" -f3-)"
		result_write "$stage" "skip" "host test build failed (${htb_detail})"
		return 0
	fi

	printf '  Running firmware host tests...\n'
	local ctest_out ctest_rc

	# Try --test-dir (cmake >= 3.20); fall back to cd + ctest
	if ctest --test-dir "$TEST_BUILD_DIR" --output-on-failure 2>&1; then
		ctest_out="$(ctest --test-dir "$TEST_BUILD_DIR" --output-on-failure 2>&1)" && ctest_rc=$? || ctest_rc=$?
	else
		ctest_out="$(cd "$TEST_BUILD_DIR" && ctest --output-on-failure 2>&1)" && ctest_rc=$? || ctest_rc=$?
	fi

	# Parse ctest summary
	local total=0 passed=0 failed=0
	if echo "$ctest_out" | grep -q "tests passed"; then
		local summary_line
		summary_line="$(echo "$ctest_out" | grep "tests passed" | tail -1)"
		# Format: "100% tests passed, 0 tests failed out of N" or "X% tests passed, Y tests failed out of N"
		total=$(echo "$summary_line" | sed -n 's/.*out of \([0-9]\+\).*/\1/p')
		failed=$(echo "$summary_line" | sed -n 's/.*\([0-9]\+\) tests failed.*/\1/p')
		if [ -z "$failed" ]; then failed=0; fi
		if [ -n "$total" ] && [ "$total" -gt 0 ]; then
			passed=$((total - failed))
		fi
	fi

	if [ "$ctest_rc" -eq 0 ]; then
		local detail
		if [ "$total" -gt 0 ]; then
			detail="${passed}/${total} tests passed"
		else
			detail="all tests passed"
		fi
		print_banner "???" "Host Tests Passed" "${detail}"
		result_write "$stage" "pass" "${detail}"
		checkpoint_write "$stage"
		return 0
	else
		local detail="${failed:-?}/${total:-?} tests failed"
		printf '  %b[FAIL]%b %s\n' "$RED" "$RESET" "$detail"
		result_write "$stage" "fail" "${detail}"
		return 1
	fi
}

# ── Stage: ESP-IDF Verification ─────────────────────────────────────────────

run_idf_verify() {
	local stage="idf-verify"
	if checkpoint_is_valid "$stage"; then
		result_write "$stage" "pass" "$(result_get_field "$stage" 3)"
		return 0
	fi

	local os
	os="$(uname -s)"

	if command -v idf.py >/dev/null 2>&1; then
		local ver
		ver="$(idf.py --version 2>/dev/null | head -1 || echo "unknown")"
		local detail="idf.py ${ver}"
		print_banner "???" "ESP-IDF Found" "${detail}"
		result_write "$stage" "pass" "${detail}"
		checkpoint_write "$stage"
		return 0
	fi

	# Not found — provide OS-specific guidance
	printf '  %b[SKIP]%b idf.py not found on PATH.\n' "$YELLOW" "$RESET"
	if [ "$os" = "Darwin" ]; then
		if command -v brew >/dev/null 2>&1 && brew info esp-idf >/dev/null 2>&1; then
			printf '  Install: brew install esp-idf\n'
		else
			printf '  See: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/get-started/index.html\n'
		fi
	else
		printf '  Try: apt install esp-idf\n'
		printf '  See: https://docs.espressif.com/projects/esp-idf/en/stable/esp32s3/get-started/index.html\n'
	fi
	result_write "$stage" "skip" "idf.py not found"
	return 0
}

# ── Stage: Firmware Target Build ────────────────────────────────────────────

run_firmware_build() {
	local stage="firmware-build"
	if checkpoint_is_valid "$stage"; then
		result_write "$stage" "pass" "$(result_get_field "$stage" 3)"
		return 0
	fi

	# Dependency: idf-verify must have passed
	local idf_line
	idf_line="$(result_get "idf-verify")"
	if [ -z "$idf_line" ]; then
		result_write "$stage" "skip" "ESP-IDF not verified yet"
		return 0
	fi
	local idf_status
	idf_status="$(echo "$idf_line" | cut -d"$RESULT_SEP" -f2)"
	if [ "$idf_status" != "pass" ]; then
		result_write "$stage" "skip" "ESP-IDF not available"
		return 0
	fi

	printf '  Building firmware target...\n'
	local build_out build_rc
	build_out="$(cd "$FIRMWARE_DIR" && idf.py build 2>&1)" && build_rc=$? || build_rc=$?

	if [ "$build_rc" -eq 0 ]; then
		print_banner "???" "Firmware Build" "target build succeeded"
		result_write "$stage" "pass" "build succeeded"
		checkpoint_write "$stage"
		return 0
	else
		printf '  %b[FAIL]%b Firmware target build failed:\n' "$RED" "$RESET"
		printf '%s\n' "$build_out" | tail -20
		printf '  Try: cd firmware && idf.py fullclean && idf.py build\n'
		result_write "$stage" "fail" "build failed"
		return 1
	fi
}

# ── Stage: ESP32-S3 Detection ──────────────────────────────────────────────

run_flash_detect() {
	local stage="flash-detect"
	if checkpoint_is_valid "$stage"; then
		result_write "$stage" "pass" "$(result_get_field "$stage" 3)"
		return 0
	fi

	# Dependency: firmware-build must have passed
	local fb_line
	fb_line="$(result_get "firmware-build")"
	if [ -z "$fb_line" ]; then
		result_write "$stage" "skip" "firmware not built yet"
		result_write "flash" "skip" "firmware not built"
		return 0
	fi
	local fb_status
	fb_status="$(echo "$fb_line" | cut -d"$RESULT_SEP" -f2)"
	if [ "$fb_status" != "pass" ]; then
		result_write "$stage" "skip" "firmware build did not succeed"
		result_write "flash" "skip" "firmware build did not succeed"
		return 0
	fi

	local os
	os="$(uname -s)"
	local device=""

	if [ "$os" = "Darwin" ]; then
		device="$(ls /dev/cu.usbmodem* /dev/cu.usbserial-* /dev/cu.wchusbserial* 2>/dev/null | head -1)"
	elif [ "$os" = "Linux" ]; then
		device="$(ls /dev/ttyUSB* /dev/ttyACM* 2>/dev/null | head -1)"
	fi

	if [ -z "$device" ]; then
		local detail="No ESP32-S3 detected on USB. Connect the board and re-run make onboard."
		printf '  %b[SKIP]%b %s\n' "$YELLOW" "$RESET" "$detail"
		result_write "$stage" "skip" "no device found"
		result_write "flash" "skip" "no device found"
		return 0
	fi

	# Check for multiple devices
	local count
	count="$(ls /dev/cu.* 2>/dev/null | wc -l | tr -d ' ')"
	if [ -n "$count" ] && [ "$count" -gt 1 ] && [ "$os" = "Darwin" ]; then
		count="$(ls /dev/cu.usbmodem* /dev/cu.usbserial-* /dev/cu.wchusbserial* 2>/dev/null | wc -l | tr -d ' ')"
		if [ -n "$count" ] && [ "$count" -gt 1 ]; then
			printf '  %b[WARN]%b Multiple serial devices found, using first: %s\n' "$YELLOW" "$RESET" "$device"
		fi
	fi

	print_banner "???" "ESP32-S3 Detected" "${device}"
	result_write "$stage" "pass" "${device}"
	checkpoint_write "$stage"
	return 0
}

# ── Stage: ESP32-S3 Flash ──────────────────────────────────────────────────

run_flash() {
	local stage="flash"
	if checkpoint_is_valid "$stage"; then
		result_write "$stage" "pass" "$(result_get_field "$stage" 3)"
		return 0
	fi

	# Dependency: flash-detect must have found a device
	local fd_line
	fd_line="$(result_get "flash-detect")"
	if [ -z "$fd_line" ]; then
		result_write "$stage" "skip" "device detection not done yet"
		return 0
	fi
	local fd_status
	fd_status="$(echo "$fd_line" | cut -d"$RESULT_SEP" -f2)"
	if [ "$fd_status" != "pass" ]; then
		local fd_detail
		fd_detail="$(echo "$fd_line" | cut -d"$RESULT_SEP" -f3-)"
		result_write "$stage" "skip" "${fd_detail}"
		return 0
	fi

	local device
	device="$(echo "$fd_line" | cut -d"$RESULT_SEP" -f3-)"

	printf '  Flashing firmware to %s...\n' "$device"
	local flash_out flash_rc
	flash_out="$(cd "$FIRMWARE_DIR" && idf.py -p "$device" flash 2>&1)" && flash_rc=$? || flash_rc=$?

	if [ "$flash_rc" -eq 0 ]; then
		print_banner "???" "Flash Complete" "device: ${device}"
		result_write "$stage" "pass" "flashed to ${device}"
		checkpoint_write "$stage"
		return 0
	else
		local os
		os="$(uname -s)"
		printf '  %b[FAIL]%b Flash failed:\n' "$RED" "$RESET"
		printf '%s\n' "$flash_out" | tail -10
		if [ "$os" = "Darwin" ]; then
			printf '  Check device permissions: sudo chmod 666 %s\n' "$device"
		else
			printf '  Check user is in dialout group: sudo usermod -a -G dialout $USER\n'
		fi
		result_write "$stage" "fail" "flash failed"
		return 1
	fi
}

# ── Init ────────────────────────────────────────────────────────────────────

init_onboard_dir() {
	mkdir -p "$ONBOARD_DIR"

	# Clean up orphaned stale checkpoints on HEAD change
	local current
	current="$(git_head)"
	if [ "$current" != "no-git-head" ]; then
		# If any checkpoint has a different HEAD, cascade-clear all subsequent
		local stages="platform-detect toolchain-verify host-test-build host-test-run idf-verify firmware-build flash-detect flash"
		local cascade=0
		for s in $stages; do
			if [ "$cascade" -eq 1 ]; then
				rm -f "${ONBOARD_DIR}/${s}.ok"
				continue
			fi
			if [ -f "${ONBOARD_DIR}/${s}.ok" ]; then
				local recorded
				recorded="$(cat "${ONBOARD_DIR}/${s}.ok")"
				if [ "$recorded" != "$current" ]; then
					rm -f "${ONBOARD_DIR}/${s}.ok"
					cascade=1
				fi
			fi
		done
	fi
}

# ── Main ────────────────────────────────────────────────────────────────────

main() {
	if [ "${1:-}" = "--status" ]; then
		if [ ! -f "$RESULTS_FILE" ] || [ ! -s "$RESULTS_FILE" ]; then
			echo "No onboard run found. Run ${BOLD}make onboard${RESET} first."
			exit 0
		fi
		render_summary
		exit 0
	fi

	printf '\n%s%s  Temper Onboard  %s\n' "$BOLD" "$CYAN" "$RESET"
	printf '%sGuided quick-start achievement run%s\n\n' "$DIM" "$RESET"

	init_onboard_dir

	# Stage execution — linear sequence with graceful degradation
	run_platform_detect
	run_toolchain_verify
	run_host_test_build
	run_host_test_run
	run_idf_verify
	run_firmware_build
	run_flash_detect
	run_flash

	# Summary
	render_summary

	# Count results
	local passed=0 failed=0 skipped=0
	if [ -f "$RESULTS_FILE" ]; then
		while IFS= read -r line; do
			case "$(echo "$line" | cut -d"$RESULT_SEP" -f2)" in
				pass) passed=$((passed + 1)) ;;
				fail) failed=$((failed + 1)) ;;
				skip) skipped=$((skipped + 1)) ;;
			esac
		done < "$RESULTS_FILE"
	fi

	printf '  %b%d passed%b  %b%d failed%b  %b%d skipped%b\n' \
		"$GREEN" "$passed" "$RESET" \
		"$RED" "$failed" "$RESET" \
		"$YELLOW" "$skipped" "$RESET"

	if [ "$failed" -gt 0 ]; then
		printf '\n  %bSome stages failed.%b Fix the issues above and re-run %bmake onboard%b.\n' \
			"$YELLOW" "$RESET" "$BOLD" "$RESET"
	elif [ "$skipped" -gt 0 ]; then
		printf '\n  %bAll runnable stages passed!%b Install missing tools and re-run %bmake onboard%b.\n' \
			"$GREEN" "$RESET" "$BOLD" "$RESET"
	else
		printf '\n  %bAll stages passed!%b Your Temper dev environment is ready.\n' \
			"$GREEN" "$RESET"
	fi
	printf '\n'
}

main "$@"
