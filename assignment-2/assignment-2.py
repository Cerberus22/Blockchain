import sys
import time
import hashlib
import argparse
from messages import *
from ipv8.peer import Peer
from ipv8_service import IPv8
from dataclasses import dataclass
from ipv8.util import run_forever
from asyncio import run, to_thread, sleep
from ipv8.lazy_community import lazy_wrapper
from ipv8.community import Community, CommunitySettings
from ipv8.messaging.payload_dataclass import DataClassPayload, type_from_format
from ipv8.configuration import (
    ConfigBuilder,
    Strategy,
    WalkerDefinition,
    default_bootstrap_defs,
)

COMMUNITY_ID = bytes.fromhex("4c61623247726f75705369676e696e6732303236")
SERVER_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3a82e33614a342774e084af80835838d6dbdb64a537d3ddb6c1d82011a7f101553cda40cf5fa0e0fc23abd0a9c4f81322282c5b34566f6b8401f5f683031e60c96"
)
AISTE_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3a2513a65668a4c90fecaab284db8c782ed99a4bcab0284902e50127c9bcafda4998739097897c8ea911a9dff86f6ca2b71d3fd9086b1c4775d6bd3d5c00c818f9"
)
AYKUT_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3ad8e3c43d2221dcef7f94eb20d566afeba009e90eb999d69511ebcbf369a3303895c92c299356298f6f115c26fb14ad994347b8447ac028640344b0abc34221cd"
)
YURIAN_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3afbc497359b4d8bc2d70fc55a3261ad831872055bd13bca87379be73cf9246e1611d4b25ac771d74cc8628d2c44c85f5de40aa9c79f2d6e9901a967063b621fc4"
)
ME_PUBLIC_KEY = None


# Parse arguments
keyfile = sys.argv[1] if len(sys.argv) > 1 else "yurian"

# Response compilations
_ = ResponseMessage(False, "", "")
_ = ChallengeResponseMessage(b"", 0, 0.0)
_ = RoundResultMessage(False, 0, 0, "")
_ = PleaseSignMessage(b"", 0)
_ = SignedMessage(b"")
_ = StartRoundMessage(0)

# Global references
server_peer = None
team_peers = [None, None, None]
team_keys = [AISTE_PUBLIC_KEY, AYKUT_PUBLIC_KEY, YURIAN_PUBLIC_KEY]
group_id = None
my_round = 0

sig_responses = {}
curr_round_number = 0


async def async_input(prompt: str = "") -> str:
    return await to_thread(input, prompt)


class DelftCommunity(Community):
    community_id = COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(ResponseMessage, self.on_response)
        self.add_message_handler(ChallengeResponseMessage, self.on_challenge_response)
        self.add_message_handler(PleaseSignMessage, self.on_please_sign)
        self.add_message_handler(SignedMessage, self.on_signed_message)
        self.add_message_handler(RoundResultMessage, self.on_round_result)
        self.add_message_handler(StartRoundMessage, self.on_start_round)

    # === RESPONSE HANDLERS ===
    @lazy_wrapper(ResponseMessage)
    def on_response(self, peer: Peer, payload: ResponseMessage) -> None:
        global group_id
        group_id = payload.group_id
        print(f"Group ID: {group_id}")
        if peer != server_peer:
            return

        payload = ChallengeRequestMessage(group_id=payload.group_id)
        self.ez_send(server_peer, payload)

    @lazy_wrapper(ChallengeResponseMessage)
    def on_challenge_response(
        self, peer: Peer, payload: ChallengeResponseMessage
    ) -> None:
        global curr_round_number
        curr_round_number = payload.round_number
        if peer != server_peer:
            return
        sig_responses.clear()
        for teammate in team_peers:
            if teammate is not None:
                request = PleaseSignMessage(payload.nonce, curr_round_number)
                self.ez_send(teammate, request)
        sig_responses[ME_PUBLIC_KEY] = self.my_peer.key.signature(payload.nonce)

    @lazy_wrapper(PleaseSignMessage)
    def on_please_sign(self, peer: Peer, payload: PleaseSignMessage) -> None:
        global curr_round_number
        signature = self.my_peer.key.signature(payload.to_sign)
        self.ez_send(peer, SignedMessage(signature))
        curr_round_number = payload.curr_round_number

    @lazy_wrapper(SignedMessage)
    def on_signed_message(self, peer: Peer, payload: SignedMessage) -> None:
        if peer.public_key.key_to_bin() in team_keys:
            sig_responses[peer.public_key.key_to_bin()] = payload.signature
        if len(sig_responses) == 3:
            request = BundleSubmissionMessage(
                group_id=group_id,
                round_number=curr_round_number,
                sig1=sig_responses[team_keys[0]],
                sig2=sig_responses[team_keys[1]],
                sig3=sig_responses[team_keys[2]],
            )
            self.ez_send(server_peer, request)

    @lazy_wrapper(RoundResultMessage)
    def on_round_result(self, peer: Peer, payload: RoundResultMessage) -> None:
        print(
            f"Round result from {peer}: \n\tsuccess={payload.success}, \n\tround_number={payload.round_number}, \n\trounds_completed={payload.rounds_completed}, \n\tmessage={payload.message}\n"
        )
        rn = payload.round_number
        if rn < 3:
            self.ez_send(team_peers[rn], StartRoundMessage(round_number=rn + 1))

    @lazy_wrapper(StartRoundMessage)
    async def on_start_round(self, peer: Peer, payload: StartRoundMessage) -> None:
        await self.create_submission_bundle()

    # === MENU OPTIONS ===
    async def request_signature(self) -> None:
        data = (await async_input("Data:")).encode()
        for teammate in team_peers:
            if teammate is not None:
                self.ez_send(teammate, PleaseSignMessage(data, curr_round_number))

    async def create_submission_bundle(self) -> None:
        await self.find_peers()
        if curr_round_number == 0 and my_round != 1:
            self.ez_send(
                team_peers[0],
                StartRoundMessage(round_number=1),
            )
            return
        payload = GroupRegistrationMessage(
            pk1=AISTE_PUBLIC_KEY, pk2=AYKUT_PUBLIC_KEY, pk3=YURIAN_PUBLIC_KEY
        )
        self.ez_send(server_peer, payload)

    async def get_my_key(self) -> None:
        print(self.my_peer.key.pub().key_to_bin().hex(), "\n")

    async def find_peers(self) -> None:
        global server_peer
        print(f"=== Peers {len(self.get_peers())} === {time.ctime()} ===")
        for peer in self.get_peers():
            print(peer, peer.public_key.key_to_bin().hex())
            for i in range(3):
                if (
                    peer.public_key.key_to_bin() == team_keys[i]
                    and team_peers[i] is None
                ):
                    team_peers[i] = peer
                    print(f"Found teammate {i+1}: {peer}")
                if (
                    peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY
                    and server_peer is None
                ):
                    server_peer = peer
                    print(f"Found server: {server_peer}")
        print("\n")

    # Starting function
    async def started(self) -> None:
        global ME_PUBLIC_KEY, server_peer, my_round
        ME_PUBLIC_KEY = self.my_peer.key.pub().key_to_bin()
        my_round = team_keys.index(ME_PUBLIC_KEY) + 1


async def start_client() -> None:
    global server_peer
    builder = ConfigBuilder().clear_keys().clear_overlays()
    builder.add_key("client", "curve25519", f"../{keyfile}.pem")
    builder.add_overlay(
        "DelftCommunity",
        "client",
        [WalkerDefinition(Strategy.RandomWalk, 20, {"timeout": 3.0})],
        default_bootstrap_defs,
        {},
        [("started",)],
    )
    ipv8_instance = IPv8(
        builder.finalize(), extra_communities={"DelftCommunity": DelftCommunity}
    )
    await ipv8_instance.start()

    # Wait for community to be initialized
    community = None
    for overlay in ipv8_instance.overlays:
        if isinstance(overlay, DelftCommunity):
            community = overlay
            break

    attempts = 0
    while server_peer is None:
        attempts += 1
        await sleep(1)
        for peer in community.get_peers():
            if peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY:
                server_peer = peer
                print(f"Found server peer: {server_peer} after {attempts} attempts")
                break
        if server_peer is None:
            print(f"{attempts} attempts: {len(community.get_peers())} peers")

    # Main menu loop
    while True:
        print("1. Get my public key")
        print("2. Find peers")
        print("3. Create submission bundle")
        print("4. Request signature")
        choice = 2
        try:
            choice = int(await async_input(""))
        except:
            pass
        match choice:
            case 1:
                await community.get_my_key()
            case 2:
                await community.find_peers()
            case 3:
                await community.create_submission_bundle()
            case 4:
                await community.request_signature()
            case _:
                exit(0)
        await sleep(1)


run(start_client())
