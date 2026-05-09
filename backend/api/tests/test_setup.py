import pytest
from rest_framework import status
from rest_framework.test import APIClient


@pytest.fixture
def api_client():
    return APIClient()


@pytest.mark.django_db
def test_alerts_endpoint_returns_200(api_client):
    response = api_client.get('/api/v1/alerts/')
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_clients_endpoint_returns_200(api_client):
    response = api_client.get('/api/v1/clients/')
    assert response.status_code == status.HTTP_200_OK


@pytest.mark.django_db
def test_alert_summary_endpoint_returns_200(api_client):
    response = api_client.get('/api/v1/alerts/summary/')
    assert response.status_code == status.HTTP_200_OK
