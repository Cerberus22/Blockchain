import time

import globals as state
from messages import RegisterBlockchainRequest, RegisterBlockchainResponse
from constants import (
    SERVER_COMMUNITY_ID,
    SERVER_PUBLIC_KEY,
    AISTE_PUBLIC_KEY,
    AYKUT_PUBLIC_KEY,
    YURIAN_PUBLIC_KEY,
    group_id,
    CHAIN_COMMUNITY_ID,
)

from ipv8.peer import Peer
from ipv8.community import Community, CommunitySettings
from ipv8.lazy_community import lazy_wrapper


class DelftCommunity(Community):
    community_id = SERVER_COMMUNITY_ID

    def __init__(self, settings: CommunitySettings) -> None:
        super().__init__(settings)
        self.add_message_handler(RegisterBlockchainResponse, self.on_register_blockchain_response)

    @lazy_wrapper(RegisterBlockchainResponse)
    def on_register_blockchain_response(self, peer: Peer, payload: RegisterBlockchainResponse) -> None:
        print(
            f"Register Blockchain Response:"
            f"\n\tsuccess={payload.success}"
            f"\n\tmessage={payload.message}"
        )

    async def register_blockchain(self) -> None:
        """Send a registration request to the Delft server peer."""
        message = RegisterBlockchainRequest(group_id.hex(), CHAIN_COMMUNITY_ID)
        self.ez_send(state.server_peer, message)

    async def get_my_key(self) -> None:
        print(self.my_peer.key.pub().key_to_bin().hex())

    async def find_peers(self) -> None:
        print(f"=== Delft Community Peers: {len(self.get_peers())} === {time.ctime()} ===")
        for peer in self.get_peers():
            print(
                peer,
                f"...{peer.public_key.key_to_bin().hex()[-10:]}",
                f"{' <-- SERVER' if peer.public_key.key_to_bin() == SERVER_PUBLIC_KEY else ''}",
                f"{' <-- Aiste' if peer.public_key.key_to_bin() == AISTE_PUBLIC_KEY else ''}",
                f"{' <-- Aykut' if peer.public_key.key_to_bin() == AYKUT_PUBLIC_KEY else ''}",
                f"{' <-- Yurian' if peer.public_key.key_to_bin() == YURIAN_PUBLIC_KEY else ''}",
            )
        print()

    async def started(self) -> None:
        state.ME_PUBLIC_KEY = self.my_peer.key.pub().key_to_bin()
