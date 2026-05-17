import sys

import pytest
from rest_framework.test import APIClient


@pytest.mark.unit
def test_healthz_returns_ok():
    client = APIClient()
    response = client.get('/healthz')

    assert response.status_code == 200
    assert response.json() == {'status': 'ok'}


@pytest.mark.django_db
@pytest.mark.unit
def test_readyz_returns_503_when_redis_unreachable(monkeypatch):
    class DummyRedis:
        @classmethod
        def from_url(cls, *args, **kwargs):
            raise ConnectionError('redis unreachable')

    fake_redis = type(sys)('redis')
    fake_redis.Redis = DummyRedis
    monkeypatch.setitem(sys.modules, 'redis', fake_redis)

    client = APIClient()
    response = client.get('/readyz')

    assert response.status_code == 503
    body = response.json()
    assert body['status'] == 'fail'
    assert 'redis' in body['checks']
    assert body['checks']['redis'].startswith('fail:')
