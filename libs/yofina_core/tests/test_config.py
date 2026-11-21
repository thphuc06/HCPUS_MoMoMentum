from decimal import Decimal

import pytest

from yofina_core.config import Config, ConfigError


class FakeSsm:
    class ParameterNotFound(Exception):
        pass

    def __init__(self, params):
        self.params = params
        self.calls: list[tuple[str, bool]] = []

    def get_parameter(self, *, Name, WithDecryption):
        self.calls.append((Name, WithDecryption))
        if Name not in self.params:
            raise self.ParameterNotFound(Name)
        return {"Parameter": {"Value": self.params[Name]}}


def test_env_thang_ssm():
    ssm = FakeSsm({"/yofina/x": "tu-ssm"})
    cfg = Config({"YOFINA_X": "tu-env", "YOFINA_SSM_PREFIX": "/yofina"}, ssm)
    assert cfg.get("x") == "tu-env"
    assert ssm.calls == []


def test_doc_ssm_giai_ma_va_cache():
    ssm = FakeSsm({"/yofina/confirm_token_ttl_seconds": "120"})
    cfg = Config({"YOFINA_SSM_PREFIX": "/yofina/"}, ssm)
    assert cfg.get_int("confirm_token_ttl_seconds") == 120
    assert cfg.get_int("confirm_token_ttl_seconds") == 120
    assert ssm.calls == [("/yofina/confirm_token_ttl_seconds", True)]


def test_thieu_cau_hinh_thi_bao_loi_khong_doan():
    with pytest.raises(ConfigError, match="YOFINA_NOPE"):
        Config({}).get("nope")
    ssm = FakeSsm({})
    with pytest.raises(ConfigError):
        Config({"YOFINA_SSM_PREFIX": "/yofina"}, ssm).get("nope")


def test_default_tuong_minh():
    assert Config({}).get("nope", default=7) == 7


def test_kieu_du_lieu_va_loi_dinh_dang():
    cfg = Config({"YOFINA_A": "12", "YOFINA_B": "1.5", "YOFINA_C": "yes", "YOFINA_D": "x"})
    assert cfg.get_int("a") == 12
    assert cfg.get_decimal("b") == Decimal("1.5")
    assert cfg.get_bool("c") is True
    with pytest.raises(ConfigError):
        cfg.get_int("d")
    with pytest.raises(ConfigError):
        cfg.get_bool("d")


def test_region_phai_tuong_minh():
    assert Config({"AWS_REGION": "ap-southeast-1"}).region() == "ap-southeast-1"
    assert Config({"YOFINA_REGION": "a", "AWS_REGION": "b"}).region() == "a"
    with pytest.raises(ConfigError):
        Config({}).region()


def test_loi_ssm_khac_duoc_boc_lai():
    class Boom:
        def get_parameter(self, **_):
            raise RuntimeError("mạng đứt")

    with pytest.raises(ConfigError, match="mạng đứt"):
        Config({"YOFINA_SSM_PREFIX": "/y"}, Boom()).get("x")
