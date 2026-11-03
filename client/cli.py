"""Polling test client.

    uv run python client/cli.py            # listen for new WhatsApp messages
    uv run python client/cli.py --manual   # submit one sample review via the API
"""
import json
import sys
import time

import requests

BASE_URL = "http://127.0.0.1:8000/review/"
POLL_SECONDS = 1
JOB_TIMEOUT = 180        # give up on a single job after this many seconds
REPLY_WAIT = 20          # how long to wait for the WhatsApp send outcome
TERMINAL_STATUSES = {"failed", "blocked", "needs_review"}


def get_latest() -> dict | None:
    resp = requests.get(f"{BASE_URL}latest", timeout=10)
    return resp.json() if resp.status_code == 200 else None


def get_job(job_id: str) -> dict | None:
    resp = requests.get(f"{BASE_URL}{job_id}", timeout=10)
    return resp.json() if resp.status_code == 200 else None


def submit_manual(text: str) -> str:
    """Testing mode: send the review straight to the API (no WhatsApp)."""
    resp = requests.post(BASE_URL, json={"review": text}, timeout=10)
    resp.raise_for_status()
    return resp.json()["job_id"]


def is_finished(data: dict, started: float) -> bool:
    if data["status"] in TERMINAL_STATUSES:
        return True
    if data["status"] != "done":
        return False

    if data.get("sentiment") == "negative":
        pending = "pending" in (data.get("ticket_copy_status"), data.get("hubspot_ticket"))
    else:
        pending = data.get("reply_status") == "pending"

    # sends and ticket creation are separate tasks: wait for them, but not forever
    return not pending or time.time() - started > REPLY_WAIT


def print_result(job_id: str, data: dict) -> None:
    print("\n" + "=" * 50)
    print("Job:", job_id)

    status = data["status"]
    if status == "failed":
        print("FAILED:", data.get("error"))
        return
    if status == "blocked":
        print("BLOCKED by input guardrail:", data.get("reason"))
        return
    if status == "needs_review":
        print("NEEDS HUMAN REVIEW (output guardrail):", data.get("reason"))
        print("Message:", data.get("review"))
        print("Sentiment:", data.get("sentiment"))
        return

    print("Message:", data["review"])
    print("Sentiment:", data["sentiment"])

    if data["sentiment"] == "negative":
        print("Ticket JSON:")
        print(json.dumps(data["ticket_json"], indent=4))
        print("Ticket copy sent to user:", data.get("ticket_copy_status"))

        hs = data.get("hubspot_ticket")
        if isinstance(hs, dict):
            print("HubSpot ticket:", hs["url"])
            if hs.get("contact_error"):
                print("  (contact link failed:", hs["contact_error"], ")")
        else:
            print("HubSpot ticket:", hs)
    else:
        print("Customer Reply:")
        print(data["reply"])
        print("Reply status:", data.get("reply_status"))
    print("=" * 50)


def run_manual() -> None:
    text = (
        "I was charged twice for my subscription this month. "
        "I expect a prompt refund for the overcharge, and I want "
        "this escalated to your billing manager before I file "
        "a dispute with my bank. You can look up my account under "
        "Elena Rostova, email address: elena.ros@globalcorp.io."
    )
    job_id = submit_manual(text)
    print("Job submitted:", job_id)
    started = time.time()
    while time.time() - started < JOB_TIMEOUT:
        data = get_job(job_id)
        if data and is_finished(data, started):
            print_result(job_id, data)
            return
        time.sleep(POLL_SECONDS)
    print("Timed out waiting for the worker. Is Celery running?")


def run_forever() -> None:
    print("Listening for new WhatsApp messages... (Ctrl+C to stop)")

    last_seen = None
    pending: dict[str, float] = {}   # job_id -> time we first saw it
    api_down = False

    # start from "now": ignore jobs that existed before the client started
    while True:
        try:
            latest = get_latest()
            last_seen = latest["job_id"] if latest else None
            break
        except requests.exceptions.RequestException:
            print("API not reachable, retrying...")
            time.sleep(3)

    while True:
        try:
            latest = get_latest()
            if latest and latest["job_id"] != last_seen:
                last_seen = latest["job_id"]
                pending[last_seen] = time.time()
                print(f"\nNew WhatsApp message -> job {last_seen}, processing...")

            for job_id, started in list(pending.items()):
                data = get_job(job_id)

                if data is None:
                    print(f"Job {job_id} expired or not found.")
                    del pending[job_id]
                elif is_finished(data, started):
                    print_result(job_id, data)
                    del pending[job_id]
                elif time.time() - started > JOB_TIMEOUT:
                    print(f"Job {job_id} timed out (status: {data['status']}). Is Celery running?")
                    del pending[job_id]

            if api_down:
                print("API is back.")
                api_down = False

        except requests.exceptions.RequestException:
            if not api_down:
                print("API not reachable, retrying...")
                api_down = True

        time.sleep(POLL_SECONDS)


def main() -> None:
    try:
        if "--manual" in sys.argv:
            run_manual()
        else:
            run_forever()
    except KeyboardInterrupt:
        print("\nStopped.")


if __name__ == "__main__":
    main()
