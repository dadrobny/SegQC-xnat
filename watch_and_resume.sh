#!/usr/bin/env bash
# Restart the queue runner whenever limits reset

INTERVAL=300
WAIT=900

is_rate_limited() {
    claude -p "." 2>&1 | grep -qiE "rate.?limit|usage.?limit|overload|429|quota"
}

while true; do
    if is_rate_limited; then
        echo "[$(date)] Limited — waiting ${WAIT}s..."
        sleep "$WAIT"
    else
        echo "[$(date)] Running queue..."
        # This starts a fresh Claude Code session that picks up the queue
        claude -p "/aide-run-queue"
        echo "[$(date)] Queue run exited. Rechecking in ${INTERVAL}s..."
        sleep "$INTERVAL"
    fi
done
