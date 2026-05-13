import argparse
import hashlib
from asyncio import Future, run, to_thread, sleep, get_running_loop, run_coroutine_threadsafe
from dataclasses import dataclass
import time
from threading import Thread

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
    ""
)

# Global reference to the community for main thread access
ipv8_instance = None
client_loop = None

class DelftCommunity(Community):
    community_id = COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)

    def started(self) -> None:
        # self.register_task("hashable1", self.create_submission_bundle, interval=1, delay=0)
        pass
    
    # Things to do
    async def create_submission_bundle(self) -> None:
        pass

    async def get_my_key(self) -> None:
        print(self.my_peer.key.pub().key_to_bin().hex(), "\n")

    async def find_peers(self) -> None:
        print(f"=== Peers {len(self.get_peers())} === {time.ctime()} ===")
        for peer in self.get_peers():
            print(peer, peer.public_key.key_to_bin().hex()[-30:])
        print("\n")

async def start_client() -> None:
    global ipv8_instance, client_loop
    
    client_loop = get_running_loop()
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

    await sleep(float('inf'))

def _run_client_loop() -> None:
    run(start_client())

client_thread = Thread(target=_run_client_loop, name="client-thread", daemon=True)
client_thread.start()

time.sleep(1)
community = None
for overlay in ipv8_instance.overlays:
    if isinstance(overlay, DelftCommunity):
        community = overlay
        break

while True:
    print("1. Get my public key")
    print("2. Find peers")
    choice = int(input(""))
    match choice:
        case 1:
            run_coroutine_threadsafe(community.get_my_key(), client_loop)
        case 2:
            run_coroutine_threadsafe(community.find_peers(), client_loop)
        case _: 
            exit(0)
    time.sleep(1)        
