import logging
import os
import httpx

logger = logging.getLogger("consul_helper")

CONSUL_URL = os.getenv("CONSUL_URL", "http://localhost:8500")

# Static fallback map for local/test environment when Consul is offline
STATIC_FALLBACKS = {
    "user-service": os.getenv("USER_SERVICE_URL", "http://localhost:8000"),
    "product-service": os.getenv("PRODUCT_SERVICE_URL", "http://localhost:8001"),
    "cart-service": os.getenv("CART_SERVICE_URL", "http://localhost:8002"),
    "order-service": os.getenv("ORDER_SERVICE_URL", "http://localhost:8003"),
    "payment-service": os.getenv("PAYMENT_SERVICE_URL", "http://localhost:8004"),
    "notification-service": os.getenv("NOTIFICATION_SERVICE_URL", "http://localhost:8005"),
}


class ConsulClient:
    def __init__(self, consul_url: str = CONSUL_URL):
        self.consul_url = consul_url

    def register_service(self, name: str, service_id: str, host: str, port: int) -> bool:
        """Register service with Consul and setup Health Check."""
        url = f"{self.consul_url}/v1/agent/service/register"
        # Health check endpoint of the service
        check_url = f"http://{host}:{port}/health"

        payload = {
            "ID": service_id,
            "Name": name,
            "Address": host,
            "Port": port,
            "Check": {
                "HTTP": check_url,
                "Interval": "10s",
                "Timeout": "5s",
                "DeregisterCriticalServiceAfter": "30s"
            }
        }
        try:
            resp = httpx.put(url, json=payload, timeout=5.0)
            if resp.status_code == 200:
                logger.info(f"Successfully registered {service_id} to Consul.")
                return True
            logger.error(f"Failed to register to Consul: {resp.text}")
        except Exception as e:
            logger.warning(f"Consul unavailable for registration ({e}). Running without Consul registration.")
        return False

    def deregister_service(self, service_id: str) -> bool:
        """Deregister service from Consul."""
        url = f"{self.consul_url}/v1/agent/service/deregister/{service_id}"
        try:
            resp = httpx.put(url, timeout=5.0)
            if resp.status_code == 200:
                logger.info(f"Successfully deregistered {service_id} from Consul.")
                return True
            logger.error(f"Failed to deregister from Consul: {resp.text}")
        except Exception as e:
            logger.warning(f"Consul unavailable for deregistration ({e}).")
        return False

    def resolve_service(self, name: str) -> str:
        """Resolve dynamic URL of the healthiest service instance. Fallback to static URL if error/not found."""
        url = f"{self.consul_url}/v1/health/service/{name}?passing=true"
        try:
            resp = httpx.get(url, timeout=3.0)
            if resp.status_code == 200:
                instances = resp.json()
                if instances:
                    # Get the first instance (simple client-side load balancing)
                    service_data = instances[0]["Service"]
                    addr = service_data["Address"]
                    port = service_data["Port"]
                    resolved_url = f"http://{addr}:{port}"
                    logger.info(f"Resolved {name} dynamically via Consul: {resolved_url}")
                    return resolved_url
        except Exception as e:
            logger.warning(f"Consul query failed for {name} ({e}). Falling back to static route.")

        # Fallback mechanism
        fallback_url = STATIC_FALLBACKS.get(name)
        if fallback_url:
            logger.info(f"Consul fallback: resolved {name} statically: {fallback_url}")
            return fallback_url

        raise Exception(f"Unable to resolve service location for '{name}' (Consul query failed & no static fallback found).")


# Shared client singleton
consul_client = ConsulClient()
