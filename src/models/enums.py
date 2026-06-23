from enum import Enum

class AssetType(str, Enum):
    domain = "domain"
    subdomain = "subdomain"
    ip_address = "ip_address"
    service = "service"
    certificate = "certificate"
    technology = "technology"

class AssetStatus(str, Enum):
    active = "active"
    stale = "stale"
    archived = "archived"