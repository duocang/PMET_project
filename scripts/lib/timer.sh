#!/bin/bash

# Timer utilities for measuring and displaying elapsed time
# 计时工具 - 用于测量和显示经过的时间

# Display elapsed time in a human-readable format
# 以人性化格式显示经过的时间
# Usage: print_elapsed_time $start_time_seconds
# Example: print_elapsed_time $SECONDS
function print_elapsed_time() {
    local start_time=$1
    local end_time=$SECONDS
    local elapsed_time=$((end_time - start_time))

    local days=$((elapsed_time / 86400))
    local hours=$(( (elapsed_time % 86400) / 3600 ))
    local minutes=$(( (elapsed_time % 3600) / 60 ))
    local seconds=$((elapsed_time % 60))

    print_orange "\n\nTime taken: $days day $hours hour $minutes minute $seconds second\n"
}

# Display a formatted elapsed time with optional status message
# 显示格式化的经过时间，可选状态消息
# Usage: print_elapsed_time_with_status $start_time_seconds "success|error" [error_message]
# Example: print_elapsed_time_with_status $start_time "success"
function print_elapsed_time_with_status() {
    local start_time=$1
    local status=$2
    local error_message=${3:-}

    local end_time=$SECONDS
    local elapsed_time=$((end_time - start_time))

    local days=$((elapsed_time / 86400))
    local hours=$(( (elapsed_time % 86400) / 3600 ))
    local minutes=$(( (elapsed_time % 3600) / 60 ))
    local seconds=$((elapsed_time % 60))

    if [[ "$status" == "success" ]]; then
        print_orange "\n\nTime taken: $days day $hours hour $minutes minute $seconds second\n"
    elif [[ "$status" == "error" ]]; then
        print_red "Error: $error_message"
        print_orange "Time taken: $days day $hours hour $minutes minute $seconds second\n"
    fi
}
