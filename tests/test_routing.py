from core.models import ServiceType
from dispatcher.agent import route_query
from core.kb_loader import load_all_kbs

def test_kb_loader():
    kbs = load_all_kbs()
    assert len(kbs) >= 7  # Ожидаем, что загрузится большинство из 9 сервисов
    assert "water_supply" in kbs
    assert "gas_supply" in kbs

def test_routing_gas():
    history = [{"role": "user", "content": "Пахнет газом на кухне!"}]
    res = route_query(history)
    assert res.service == ServiceType.GAS_SUPPLY
    assert res.confidence >= 0.7

def test_routing_electricity():
    history = [{"role": "user", "content": "Искрит розетка в спальне"}]
    res = route_query(history)
    assert res.service == ServiceType.ELECTRICITY_SUPPLY
    assert res.confidence >= 0.7

if __name__ == "__main__":
    print("Testing KB Loader...")
    test_kb_loader()
    print("Testing Gas Routing...")
    test_routing_gas()
    print("Testing Electricity Routing...")
    test_routing_electricity()
    print("ALL TESTS PASSED SUCCESSFULLY.")
