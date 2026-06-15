from dataclasses import dataclass
from custom_types import *
from ipv8.messaging.payload_dataclass import DataClassPayload


# === DELFT COMMUNITY MESSAGES ===
@dataclass
class RegisterBlockchainRequest(DataClassPayload[1]):
    group_id: str
    community_id: bytes


@dataclass
class RegisterBlockchainResponse(DataClassPayload[2]):
    success: bool
    message: str


# === BLOCKCHAIN COMMUNITY MESSAGES ===
@dataclass
class SubmitTransactionRequest(DataClassPayload[1]):
    sender_key: bytes
    data: bytes
    timestamp: int
    signature: bytes


@dataclass
class SubmitTransactionResponse(DataClassPayload[2]):
    success: bool
    tx_hash: bytes
    message: str


@dataclass
class GetChainHeigthRequest(DataClassPayload[3]):
    request_id: int


@dataclass
class GetChainHeigthResponse(DataClassPayload[4]):
    request_id: int
    height: int
    tip_hash: bytes


@dataclass
class GetBlockRequest(DataClassPayload[5]):
    height: int


@dataclass
class GetBlockResponse(DataClassPayload[6]):
    height: int
    prev_hash: bytes
    txs_hash: bytes
    timestamp: int
    difficulty: int
    nonce: int
    block_hash: bytes
    tx_hashes: bytes


@dataclass
class BlockAnnouncementMessage(DataClassPayload[7]):
    height: int
    block: bytes


@dataclass
class ChangedDifficultyMessage(DataClassPayload[8]):
    new_difficulty: int


@dataclass
class EntireChainRequest(DataClassPayload[9]):
    request_id: int
    height: int


@dataclass
class EntireChainResponse(DataClassPayload[10]):
    request_id: int
    total_height: int
    height: int
    block: bytes


# Force serializer format registration for all payload types
_ = RegisterBlockchainResponse(False, "")
_ = SubmitTransactionRequest(b"", b"", 0, b"")
_ = SubmitTransactionResponse(False, b"", "")
_ = GetChainHeigthRequest(0)
_ = GetBlockRequest(0)
_ = GetChainHeigthResponse(0, 0, b"")
_ = GetBlockResponse(0, b"", b"", 0, 0, 0, b"", b"")
_ = ChangedDifficultyMessage(0)
_ = BlockAnnouncementMessage(0, b"")
_ = EntireChainRequest(0, 0)
_ = EntireChainResponse(0, 0, 0, b"")
