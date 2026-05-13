import argparse
import hashlib
from asyncio import Future, run, to_thread
from dataclasses import dataclass

from ipv8.community import Community, CommunitySettings
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.payload_dataclass import DataClassPayload, type_from_format
from ipv8.peer import Peer
from ipv8.util import run_forever
from ipv8_service import IPv8

COMMUNITY_ID = bytes.fromhex("2c1cc6e35ff484f99ebdfb6108477783c0102881")
SERVER_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3a86b23934a28d669c390e2d1fc0b0870706c4591cc0cb"
    "178bc5a811da6d87d27ef319b2638ef60cc8d119724f4c53a1ebfad919c3ac41"
    "36c501ce5c09364e0ebb"
)
DIFFICULTY_BITS = 28
INT64 = type_from_format("q")

EMAIL = "Y.G.Lagrang@student.tudelft.nl"
GITHUB_URL = "https://github.com/Cerberus22/Blockchain/"
RESULT_FUTURE: Future[bool] | None = None


def leading_zero_bits(digest: bytes) -> int:
    bits = 0
    for byte in digest:
        if byte == 0:
            bits += 8
            continue
        bits += 8 - byte.bit_length()
        break
    return bits


def solve_pow(email: str, github_url: str, difficulty_bits: int) -> tuple[int, bytes]:
    prefix = email.encode("utf-8") + b"\n" + github_url.encode("utf-8") + b"\n"

    for nonce in range(0, (1 << 63) - 1):
        nonce = 138636582
        digest = hashlib.sha256(prefix + nonce.to_bytes(8, "big", signed=False)).digest()
        if leading_zero_bits(digest) >= difficulty_bits:
            return nonce, digest

    raise RuntimeError("No valid nonce found within int64 non-negative range.")


@dataclass
class SubmissionPayload(DataClassPayload[1]):
    email: str
    github_url: str
    nonce: INT64


@dataclass
class ResponsePayload(DataClassPayload[2]):
    success: bool
    message: str


# Pre-compile payload metadata so incoming messages can be unpacked
# before any local instance of the payload classes is created.
_ = SubmissionPayload("", "", 0)
_ = ResponsePayload(False, "")


class DelftCommunity(Community):
    community_id = COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(ResponsePayload, self.on_response)
        self.submitted = False

    def started(self) -> None:
        self.register_task("try_submit", self.try_submit, interval=2.0, delay=0)

    @lazy_wrapper(ResponsePayload)
    def on_response(self, peer: Peer, payload: ResponsePayload) -> None:
        print(payload)

        if peer.public_key.key_to_bin() != SERVER_PUBLIC_KEY:
            return

        print(f"Server response: success={payload.success}, message={payload.message}")
        if RESULT_FUTURE is not None and not RESULT_FUTURE.done():
            RESULT_FUTURE.set_result(payload.success)

    async def try_submit(self) -> None:
        if self.submitted:
            return

        server_peer = None
        for peer in self.get_peers():
            if peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY:
                server_peer = peer
                break

        if server_peer is None:
            return

        nonce, digest = await to_thread(solve_pow, EMAIL, GITHUB_URL, DIFFICULTY_BITS)
        self.ez_send(server_peer, SubmissionPayload(EMAIL, GITHUB_URL, nonce))
        self.submitted = True
        print("Submission sent. Waiting for server response...")


async def start_client() -> None:
    global RESULT_FUTURE

    RESULT_FUTURE = Future()

    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.add_key("client", "curve25519", "../client.pem")
    builder.add_overlay(
        "DelftCommunity",
        "client",
        [WalkerDefinition(Strategy.RandomWalk, 20, {"timeout": 3.0})],
        default_bootstrap_defs,
        {},
        [("started",)],
    )
    await IPv8(builder.finalize(),
        extra_communities={"DelftCommunity": DelftCommunity}
    ).start()

    await run_forever()

run(start_client())