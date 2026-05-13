import argparse
import hashlib
from asyncio import run, to_thread, sleep
from dataclasses import dataclass
import time
from messages import *

from ipv8.community import Community, CommunitySettings
from ipv8.configuration import ConfigBuilder, Strategy, WalkerDefinition, default_bootstrap_defs
from ipv8.lazy_community import lazy_wrapper
from ipv8.messaging.payload_dataclass import DataClassPayload, type_from_format
from ipv8.peer import Peer
from ipv8.util import run_forever
from ipv8_service import IPv8

COMMUNITY_ID = bytes.fromhex("4c61623247726f75705369676e696e6732303236")
SERVER_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3a82e33614a342774e084af80835838d6dbdb64a537d3ddb6c1d82011a7f101553cda40cf5fa0e0fc23abd0a9c4f81322282c5b34566f6b8401f5f683031e60c96"
)
AYKUT_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3ad8e3c43d2221dcef7f94eb20d566afeba009e90eb999d69511ebcbf369a3303895c92c299356298f6f115c26fb14ad994347b8447ac028640344b0abc34221cd"
)
AISTE_PUBLIC_KEY = bytes.fromhex(
    "4c69624e61434c504b3a4924a5ac3d83e3128007c5a349dcbda9396f45fc0331f4cd84cf5b7ec3f7b20339cafc465a0f36ddb65c4295953d01327921d7ab4ea5a7e69dcb5e16b96e0ca3"
)
ME_PUBLIC_KEY = None

# Response compilations
_ = ResponseMessage(False, "", "")

# Global references
server_peer = None

class DelftCommunity(Community):
    community_id = COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(ResponseMessage, self.on_response)
        self.add_message_handler(ChallengeResponseMessage, self.on_challenge_response)

    # === RESPONSE HANDLERS ===
    @lazy_wrapper(ResponseMessage)
    def on_response(self, peer: Peer, payload: ResponseMessage) -> None:
        print(f"Response from {peer}: \n\tsuccess={payload.success}, \n\tgroup_id={payload.group_id}, \n\tmessage={payload.message}\n")
        if peer != server_peer:
            return

        payload = ChallengeRequestMessage(group_id=payload.group_id)
        self.ez_send(server_peer, payload)

    @lazy_wrapper(ChallengeResponseMessage)
    def on_challenge_response(self, peer: Peer, payload: ChallengeResponseMessage) -> None:
        print(f"Challenge response from {peer}: \n\tnonce={payload.nonce.hex()}, \n\tround_number={payload.round_number}, \n\tdeadline={time.ctime(payload.deadline)}\n")
        if peer != server_peer:
            return

    # === MENU OPTIONS ===
    async def create_submission_bundle(self) -> None:
        payload = GroupRegistrationMessage(
            pk1=ME_PUBLIC_KEY,
            pk2=AYKUT_PUBLIC_KEY,
            pk3=AISTE_PUBLIC_KEY
        )
        print(server_peer)
        self.ez_send(server_peer, payload)

    async def get_my_key(self) -> None:
        print(self.my_peer.key.pub().key_to_bin().hex(), "\n")

    async def find_peers(self) -> None:
        print(f"=== Peers {len(self.get_peers())} === {time.ctime()} ===")
        for peer in self.get_peers():
            print(peer, peer.public_key.key_to_bin().hex())
        print("\n")


    # Starting function
    async def started(self) -> None:
        global ME_PUBLIC_KEY, server_peer
        ME_PUBLIC_KEY = self.my_peer.key.pub().key_to_bin()

        attempts = 0
        while server_peer is None:
            await sleep(0.1)
            for peer in self.get_peers():
                if peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY:
                    server_peer = peer
                    print(f"Found server peer: {server_peer} after {attempts} attempts")
                    break
            attempts += 1
            if attempts % 50 == 0:
                print(f"{attempts} attempts")
    

async def start_client() -> None:
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
    ipv8_instance = IPv8(builder.finalize(),
        extra_communities={"DelftCommunity": DelftCommunity}
    )
    await ipv8_instance.start()

    # Wait for community to be initialized
    community = None
    for overlay in ipv8_instance.overlays:
        if isinstance(overlay, DelftCommunity):
            community = overlay
            break

    # Main menu loop
    while True:
        print("1. Get my public key")
        print("2. Find peers")
        print("3. Create submission bundle")
        choice = 2
        try:
            choice = int(input(""))
        except:
            pass
        match choice:
            case 1:
                await community.get_my_key()
            case 2:
                await community.find_peers()
            case 3:
                await community.create_submission_bundle()
            case _: 
                exit(0)
        await sleep(1)


run(start_client())
