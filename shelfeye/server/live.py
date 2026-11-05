"""Live view, relayed through the server.

The camera can't be reached from the internet, so it comes to us instead:
  1. It keeps a request open to /live/wait, which answers as soon as someone
     opens the live view (or after WAIT_SECONDS, and it simply asks again).
  2. While someone is watching, it uploads JPEG frames to /live/frame. Each
     reply says whether anyone is still watching, so it knows when to stop.
  3. Viewers get those frames as an MJPEG stream from /stream.

Frames only live in this process's memory, so run the server with one worker.
"""
import asyncio

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from fastapi.responses import StreamingResponse

from auth import check_device_token, current_user

WAIT_SECONDS = 25  # how long a camera's /live/wait request is held open
FIRST_FRAME_SECONDS = 30  # the camera needs a few seconds to notice and switch to video
NEXT_FRAME_SECONDS = 15  # end a stream when the camera stops sending
MAX_FRAME_BYTES = 2 * 1024 * 1024

router = APIRouter(prefix="/api/nodes/{node_id}")


class Channel:
    """One camera's live view: its latest frame and who is watching."""

    def __init__(self):
        self.frame = None
        self.frame_number = 0
        self.new_frame = asyncio.Condition()
        self.viewers = 0
        self.watched = asyncio.Event()  # set while anyone is watching


_channels: dict[str, Channel] = {}


def _channel(node_id):
    if node_id not in _channels:
        _channels[node_id] = Channel()
    return _channels[node_id]


@router.get("/live/wait")
async def wait_for_viewer(node_id: str, authorization: str = Header("")):
    """Camera side: returns once someone wants to watch, or after WAIT_SECONDS."""
    check_device_token(authorization)
    channel = _channel(node_id)
    try:
        await asyncio.wait_for(channel.watched.wait(), WAIT_SECONDS)
    except asyncio.TimeoutError:
        pass
    return {"watching": channel.viewers > 0}


@router.post("/live/frame")
async def post_frame(node_id: str, request: Request, authorization: str = Header("")):
    """Camera side: one JPEG frame. The reply says whether to keep sending."""
    check_device_token(authorization)
    frame = await request.body()
    if not frame or len(frame) > MAX_FRAME_BYTES:
        raise HTTPException(status_code=400, detail="Send one JPEG frame of at most 2 MB")
    channel = _channel(node_id)
    if channel.viewers:
        async with channel.new_frame:
            channel.frame = frame
            channel.frame_number += 1
            channel.new_frame.notify_all()
    return {"watching": channel.viewers > 0}


@router.get("/stream", dependencies=[Depends(current_user)])
async def stream(node_id: str):
    """Viewer side: an MJPEG stream of the frames the camera uploads."""
    channel = _channel(node_id)
    channel.viewers += 1
    channel.watched.set()

    async def frames():
        seen = channel.frame_number  # don't show a frame left over from an earlier session
        timeout = FIRST_FRAME_SECONDS
        try:
            while True:
                async with channel.new_frame:
                    try:
                        await asyncio.wait_for(
                            channel.new_frame.wait_for(lambda: channel.frame_number != seen), timeout
                        )
                    except asyncio.TimeoutError:
                        return  # camera offline or stopped; the dashboard retries
                    seen, frame = channel.frame_number, channel.frame
                yield (
                    b"--FRAME\r\nContent-Type: image/jpeg\r\nContent-Length: "
                    + str(len(frame)).encode()
                    + b"\r\n\r\n"
                    + frame
                    + b"\r\n"
                )
                timeout = NEXT_FRAME_SECONDS
        finally:
            channel.viewers -= 1
            if channel.viewers == 0:
                channel.watched.clear()
                channel.frame = None

    return StreamingResponse(
        frames(),
        media_type="multipart/x-mixed-replace; boundary=FRAME",
        headers={"Cache-Control": "no-cache, no-store", "X-Accel-Buffering": "no"},
    )
