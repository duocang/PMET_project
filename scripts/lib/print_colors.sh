#!/bin/bash
# Colored print utilities (source this file to use)
# Provides colored output functions for terminal scripts

NC='\033[0m' # No Color

# ==================== Basic Print Functions ====================
# These functions print with a newline at the end

# Print text in red color
print_red()    { printf "\033[0;31m%b${NC}\n" "$1"; }

# Print text in green color
print_green()  { printf "\033[0;32m%b${NC}\n" "$1"; }

# Print text in orange/yellow color
print_orange() { printf "\033[0;33m%b${NC}\n" "$1"; }

# Print text in bright yellow/fluorescent yellow color
print_yellow() { printf "\033[1;33m%b${NC}\n" "$1"; }

# Print text in white color (note: no newline at the end for this function)
print_white()  { printf "\033[1;37m%b${NC}"   "$1"; }

# Alias for backward compatibility - same as print_yellow
print_fluorescent_yellow() { print_yellow "$1"; }

# ==================== Print Functions Without Newline ====================
# These functions print WITHOUT a newline at the end, useful for prompts or inline output

# Print text in green color WITHOUT newline
# Usage: print_green_no_br "Loading.."; sleep 2; print_green " Done!"
print_green_no_br() {
    printf "\033[0;32m%b${NC}" "$1"
}

# Print text in orange/yellow color WITHOUT newline
# Usage: print_orange_no_br "Choose an option [y/N]: "; read answer
print_orange_no_br() {
    printf "\033[0;33m%b${NC}" "$1"
}

# Print text in bright yellow color WITHOUT newline
# Usage: print_fluorescent_yellow_no_br "Processing: "; echo "Complete"
print_fluorescent_yellow_no_br() {
    printf "\033[1;33m%b${NC}" "$1"
}

# ==================== Special Print Functions ====================

# Print text centered on the terminal
# Calculates terminal width and centers each line in the input
# Usage: print_middle "Welcome to PMET\nVersion 1.0"
print_middle() {
    local FLUORESCENT_YELLOW='\033[1;33m'
    local NC='\033[0m'
    local COLUMNS=$(tput cols)

    while IFS= read -r line; do
        local padding=$(( (COLUMNS - ${#line}) / 2 ))
        printf "%${padding}s" ''
        printf "${FLUORESCENT_YELLOW}${line}${NC}\n"
    done <<< "$1"
}

# ==================== Error Handling ====================

# Print error message and exit with status 1
# Usage: error_exit "Database connection failed"
error_exit() {
    echo "ERROR: $1" >&2
    exit 1
}
