import pytest
from agent_helpers import make_jwt
from yofina_agent.identity import Unauthenticated, decode_jwt_payload, identity_from_authorization


def test_boc_sub_tu_header_bearer():
    token = make_jwt("11111111-2222-3333-4444-555555555555", client_id="web", token_use="access")
    ident = identity_from_authorization(f"Bearer {token}")
    assert ident.sub == "11111111-2222-3333-4444-555555555555"
    assert ident.token == token and ident.authorization == f"Bearer {token}"


def test_token_khong_lo_ra_repr():
    token = make_jwt("u1")
    assert token not in repr(identity_from_authorization(f"Bearer {token}"))


def test_scheme_khong_phan_biet_hoa_thuong_nhung_phai_la_bearer():
    token = make_jwt("u1")
    assert identity_from_authorization(f"bearer {token}").sub == "u1"
    with pytest.raises(Unauthenticated):
        identity_from_authorization(f"Basic {token}")


@pytest.mark.parametrize(
    "header",
    [None, "", "Bearer", "Bearer ", "Bearer abc", "Bearer a.b", "Bearer a.!!!.c", "Bearer a..c"],
)
def test_header_hong_bi_tu_choi(header):
    with pytest.raises(Unauthenticated):
        identity_from_authorization(header)


def test_thieu_hoac_sai_sub():
    import base64
    import json

    def tok(payload):
        seg = base64.urlsafe_b64encode(json.dumps(payload).encode()).rstrip(b"=").decode()
        return f"h.{seg}.s"

    for payload in ({}, {"sub": ""}, {"sub": 123}, {"sub": "a b"}, {"sub": "x" * 200}):
        with pytest.raises(Unauthenticated):
            identity_from_authorization(f"Bearer {tok(payload)}")
    with pytest.raises(Unauthenticated):
        decode_jwt_payload("h." + base64.urlsafe_b64encode(b"[1]").decode().rstrip("=") + ".s")
