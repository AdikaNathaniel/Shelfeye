"""Push queued readings to the ShelfEye server. Anything unsent stays queued for next time."""
import logging

import requests

log = logging.getLogger(__name__)


def send_heartbeat(server_url, node_id, token, live_view_url):
    """Tell the server this camera is alive and where its live view is.

    Returns the settings from the dashboard, or None if the server couldn't be reached.
    """
    if not server_url:
        return None
    try:
        response = requests.post(
            f"{server_url}/api/nodes/{node_id}/heartbeat",
            json={"live_view_url": live_view_url},
            headers={"Authorization": f"Bearer {token}"},
            timeout=10,
        )
        response.raise_for_status()
        return response.json().get("settings")
    except (requests.RequestException, ValueError) as exc:
        log.warning("Heartbeat failed: %s", exc)
        return None


def flush_outbox(store, server_url, node_id, token):
    if not server_url:
        return
    url = f"{server_url}/api/nodes/{node_id}/readings"
    headers = {"Authorization": f"Bearer {token}", "Content-Type": "application/json"}
    for reading_id, payload in store.pending():
        try:
            response = requests.post(url, data=payload, headers=headers, timeout=15)
        except requests.RequestException as exc:
            log.warning("Server unreachable, will retry later: %s", exc)
            return
        if response.ok:
            store.remove(reading_id)
        elif response.status_code in (400, 422):
            # The server will never accept this one, so don't let it block the queue.
            log.error("Server rejected reading %s: %s", reading_id, response.text)
            store.remove(reading_id)
        else:
            log.warning("Server returned %s, will retry later", response.status_code)
            return
