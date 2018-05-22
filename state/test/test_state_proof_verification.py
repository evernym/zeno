import random
from copy import deepcopy

import pytest

from state.db.persistent_db import PersistentDB
from state.pruning_state import PruningState
from state.state import State
from state.trie.pruning_trie import bin_to_nibbles, rlp_decode, Trie, rlp_encode
from state.util.utils import sha3
from storage.kv_in_memory import KeyValueStorageInMemory
from storage.kv_store_leveldb import KeyValueStorageLeveldb
from storage.kv_store_rocksdb import KeyValueStorageRocksdb


@pytest.yield_fixture(params=['memory', 'leveldb', 'rocksdb'])
def state(request, tmpdir_factory) -> State:
    if request.param == 'leveldb':
        db = KeyValueStorageLeveldb(tmpdir_factory.mktemp('').strpath,
                                    'some_db')
    elif request.param == 'rocksdb':
        db = KeyValueStorageRocksdb(tmpdir_factory.mktemp('').strpath,
                                    'some_db')
    else:
        db = KeyValueStorageInMemory()
    state = PruningState(db)
    yield state
    state.close()


def test_state_proof_and_verification(state):
    state.set(b'k1', b'v1')
    state.set(b'k2', b'v2')
    state.set(b'k3', b'v3')
    state.set(b'k4', b'v4')

    p1 = state.generate_state_proof(b'k1')
    p2 = state.generate_state_proof(b'k2')
    p3 = state.generate_state_proof(b'k3')
    p4 = state.generate_state_proof(b'k4')

    # Verify correct proofs and values
    assert PruningState.verify_state_proof(state.headHash, b'k1', b'v1', p1)
    assert PruningState.verify_state_proof(state.headHash, b'k2', b'v2', p2)
    assert PruningState.verify_state_proof(state.headHash, b'k3', b'v3', p3)
    assert PruningState.verify_state_proof(state.headHash, b'k4', b'v4', p4)

    # Incorrect proof
    assert PruningState.verify_state_proof(state.headHash, b'k3', b'v3', p4)

    # Correct proof but incorrect value
    assert not PruningState.verify_state_proof(state.headHash, b'k2', b'v1', p2)
    assert not PruningState.verify_state_proof(state.headHash, b'k4', b'v2', p4)


def test_state_proof_and_verification_serialized(state):
    data = {k.encode(): v.encode() for k, v in
            [('k1', 'v1'), ('k2', 'v2'), ('k35', 'v55'), ('k70', 'v99')]}

    for k, v in data.items():
        state.set(k, v)

    proofs = {k: state.generate_state_proof(k, serialize=True) for k in data}

    for k, v in data.items():
        assert PruningState.verify_state_proof(state.headHash, k, v,
                                               proofs[k], serialized=True)


def test_state_proof_for_missing_data(state):
    p1 = state.generate_state_proof(b'k1')
    assert PruningState.verify_state_proof(state.headHash, b'k1', None, p1)


def add_prefix_nodes_and_verify(state, prefix, keys_suffices=None):
    keys_suffices = keys_suffices if keys_suffices else [1, 4, 10, 11, 24, 99, 100]
    key_vals = {'{}{}'.format(prefix, k).encode():
                str(random.randint(3000, 5000)).encode() for k in keys_suffices}
    for k, v in key_vals.items():
        state.set(k, v)

    prefix_prf = state.generate_state_proof_for_key_prfx(prefix.encode())
    assert PruningState.verify_state_proof_multi(state.headHash, key_vals,
                                                 prefix_prf)


def test_state_proof_for_key_prefix(state):
    prefix = 'abcdefgh'
    add_prefix_nodes_and_verify(state, prefix)


def test_state_proof_for_key_prefix_1(state):
    prefix = 'abcdefgh'
    state.set(prefix.encode(), b'2122')
    add_prefix_nodes_and_verify(state, prefix)


def test_state_proof_for_key_prefix_2(state):
    prefix = 'abcdefgh'
    state.set((prefix[:4]+'zzzz').encode(), b'1908')
    add_prefix_nodes_and_verify(state, prefix)


def test_state_proof_for_key_prefix_3(state):
    prefix = 'abcdefgh'
    state.set(b'zyxwvuts', b'1115')
    state.set(b'rqponmlk', b'0989')
    add_prefix_nodes_and_verify(state, prefix)


def test_state_proof_for_key_prefix_4(state):
    prefix = 'abcdefgh'
    state.set(b'zyxwvuts', b'1115')
    state.set(b'rqponmlk', b'0989')
    # More than 16 suffices
    keys_suffices = {random.randint(150, 900) for _ in range(100)}
    add_prefix_nodes_and_verify(state, prefix, keys_suffices)
