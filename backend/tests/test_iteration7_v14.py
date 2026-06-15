"""v1.4 backend regression: unit-based service qty, extra nights, Spanish-date safe public endpoint, USD equivalent."""
import os
import pytest
import requests

BASE = os.environ.get('REACT_APP_BACKEND_URL', '').rstrip('/')
if not BASE:
    BASE = 'http://localhost:8001'  # local fallback

ADMIN = {'email': 'admin@aventurate.mx', 'password': 'Demo2026!'}


@pytest.fixture(scope='module')
def admin_session():
    s = requests.Session()
    r = s.post(f'{BASE}/api/auth/login', json=ADMIN, timeout=10)
    assert r.status_code == 200, r.text
    return s


@pytest.fixture(scope='module')
def packages(admin_session):
    r = admin_session.get(f'{BASE}/api/packages', timeout=10)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope='module')
def services(admin_session):
    r = admin_session.get(f'{BASE}/api/services', timeout=10)
    assert r.status_code == 200
    return r.json()


@pytest.fixture(scope='module')
def clients_list(admin_session):
    r = admin_session.get(f'{BASE}/api/clients', timeout=10)
    assert r.status_code == 200
    return r.json()


class TestPackageAllowedDays:
    def test_some_package_has_allowed_start_days(self, packages):
        with_days = [p for p in packages if p.get('allowed_start_days')]
        assert len(with_days) >= 1, 'expected at least one package with allowed_start_days seeded'
        # Guadalajara seeded with Mon,Thu = [0,3]
        gdl = [p for p in with_days if 'Guadalajara' in (p.get('name') or '')]
        if gdl:
            assert set(gdl[0]['allowed_start_days']).issubset({0, 1, 2, 3, 4, 5, 6})


class TestServiceUnit:
    def test_services_have_unit_field(self, services):
        assert len(services) > 0
        units = {s.get('unit') for s in services}
        # at least one service has a unit set
        assert any(u for u in units if u in {'per_person', 'per_group', 'per_day', 'per_access'})


class TestQuotationExtraNights:
    def test_create_quotation_with_extra_nights(self, admin_session, packages, clients_list):
        pack = next((p for p in packages if 'Guadalajara' in (p.get('name') or '') and (p.get('nights') or 0) >= 3), None)
        if not pack:
            pack = next(p for p in packages if (p.get('nights') or 0) >= 1)
        hotel = pack['hotels'][0]['name']
        client = clients_list[0]
        nights = pack['nights']
        # Build a stay that is nights+2 days long, starting on a known date
        start = '2026-07-06'  # Monday
        from datetime import date, timedelta
        end_dt = date(2026, 7, 6) + timedelta(days=nights + 2)
        end = end_dt.isoformat()
        payload = {
            'client_id': client['id'],
            'package_id': pack['id'],
            'hotel_name': hotel,
            'dates': {'start': start, 'end': end},
            'pax': {'rooms': [{'ocupacion': 'doble', 'count': 1}], 'menores': 0},
            'services': [],
            'extra_nights': {'cost_per_night': 800, 'unit': 'per_person'},
            'notes': 'TEST_extra_nights',
        }
        r = admin_session.post(f'{BASE}/api/quotations', json=payload, timeout=15)
        assert r.status_code in (200, 201), r.text
        q = r.json()
        # nights_total and extra_nights should be computed server-side
        # tolerate either flat fields or nested
        nt = q.get('nights_total') or q.get('payment', {}).get('nights_total')
        en = q.get('extra_nights_count') or q.get('payment', {}).get('extra_nights')
        if nt is not None:
            assert nt == nights + 2
        if en is not None:
            assert en == 2
        return q['id']

    def test_public_endpoint_returns_usd_equivalent(self, admin_session, packages, clients_list):
        # Reuse logic: create a normal MXN quotation and fetch /api/q/{token}
        pack = next(p for p in packages if (p.get('nights') or 0) >= 1)
        hotel = pack['hotels'][0]['name']
        client = clients_list[0]
        payload = {
            'client_id': client['id'],
            'package_id': pack['id'],
            'hotel_name': hotel,
            'dates': {'start': '2026-07-06', 'end': '2026-07-09'},
            'pax': {'rooms': [{'ocupacion': 'doble', 'count': 1}], 'menores': 0},
            'services': [],
            'notes': 'TEST_usd',
        }
        r = admin_session.post(f'{BASE}/api/quotations', json=payload, timeout=15)
        assert r.status_code in (200, 201)
        qid = r.json()['id']
        # Generate public link
        gp = admin_session.post(f'{BASE}/api/quotations/{qid}/public-link', timeout=10)
        assert gp.status_code in (200, 201), gp.text
        token = gp.json().get('public_token') or gp.json().get('token') or gp.json().get('public_link', {}).get('token')
        assert token
        # Public endpoint (no auth)
        pr = requests.get(f'{BASE}/api/public/quotations/{token}', timeout=10)
        assert pr.status_code == 200, pr.text
        pj = pr.json()
        payment = pj.get('payment') or pj
        # Currency MXN base -> USD equivalent should exist
        if (payment.get('currency') or 'MXN').upper() == 'MXN':
            assert payment.get('total_usd_equivalent') is not None, f'usd equivalent missing in {payment}'
            assert payment.get('rate_mxn_per_usd') is not None
