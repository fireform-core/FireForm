import psutil
from pydantic import BaseModel

class RoutingDecision(BaseModel):
    target: str
    available_ram: float

def get_routing_decision():
    # Check available RAM in GB
    ram = psutil.virtual_memory().available / (1024 ** 3)
    # If more than 5GB, use Local. Otherwise, Cloud.
    target = "local" if ram > 5.0 else "cloud"
    return RoutingDecision(target=target, available_ram=round(ram, 2))

if __name__ == "__main__":
    print(get_routing_decision().model_dump())
